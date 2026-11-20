/**
 * Manage durable agent runs, genuine streaming, polling fallback, cancellation, and conversation history.
 *
 * Expose startRun, cancelRun, resetConversation, and retryLastTurn. Track the active run
 * in chrome.storage.session so that reopening the side panel recovers polling/streaming.
 *
 * Stream real-time execution events: activity states ("Searching the paper", "Reading sources",
 * "Writing an answer"), real tool calls with arguments and results, and incremental answer deltas.
 * Fall back gracefully to polling when streaming is unavailable.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { ApiClient } from '../api/client';
import {
  AgentRunResponse,
  SavedConversation,
  ResearchLevel, ChatBudget, CHAT_TOKEN_LIMIT,
  AgentRunEvent,
  AnswerBlock,
  EvidenceItem,
} from '../api/types';

export interface HistoryTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface ToolActivity {
  id: string;
  toolName: string;
  state: 'running' | 'completed' | 'failed';
  arguments?: Record<string, any>;
  summary?: string;
  count?: number;
}

export interface ComposerAttachment {
  id: string;
  name: string;
  size: number;
  type: string;
  dataUrl?: string;
  textSnippet?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  attachments?: ComposerAttachment[];
  status?: AgentRunResponse['status'];
  answerBlocks?: AnswerBlock[];
  followUps?: string[];
  evidence?: EvidenceItem[];
  servingModel?: string | null;
  fallbackReason?: string | null;
  limitations?: string | null;
  error?: string | null;
  activityState?: string | null;
  toolActivities?: ToolActivity[];
  isStreaming?: boolean;
}

export interface UseAgentRunOptions {
  client: ApiClient;
  paperId: string | null;
  arxivId?: string | null;
  version?: string | null;
  canonicalUrl?: string | null;
  pollIntervalMs?: number;
  ownerId?: string;
}

export interface UseAgentRunReturn {
  budget: ChatBudget;
  runId: string | null;
  status: AgentRunResponse['status'] | null;
  polling: boolean;
  activeStep: string | null;
  answerBlocks: AnswerBlock[];
  evidence: EvidenceItem[];
  servingModel: string | null;
  fallbackReason: string | null;
  limitations: string | null;
  errorMessage: string | null;
  history: HistoryTurn[];
  // Conversational additions
  messages: ChatMessage[];
  streamingText: string;
  toolActivities: ToolActivity[];
  activityState: string | null;
  startRun: (
    question: string,
    mode?: string,
    attachments?: ComposerAttachment[],
    overridePaperId?: string,
    level?: ResearchLevel
  ) => Promise<void>;
  cancelRun: () => Promise<void>;
  resetConversation: () => void;
  retryLastTurn: () => Promise<void>;
  restoreConversation: (conversation: SavedConversation) => void;
}

const EMPTY_BUDGET: ChatBudget = { chat_id: null, tokens_used: 0, token_limit: CHAT_TOKEN_LIMIT, usage_estimated: false, chat_exhausted: false };

const SESSION_STORAGE_KEY = 'paperlens_active_agent_run';
const MAX_HISTORY_TURNS = 12; // 3 full round-trips (user + assistant)

function findLastIndex<T>(arr: T[], predicate: (item: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (predicate(arr[i])) return i;
  }
  return -1;
}

export function useAgentRun({
  client,
  paperId,
  arxivId,
  version,
  canonicalUrl,
  pollIntervalMs = 800,
  ownerId,
}: UseAgentRunOptions): UseAgentRunReturn {
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<AgentRunResponse['status'] | null>(null);
  const [polling, setPolling] = useState(false);
  const [activeStep, setActiveStep] = useState<string | null>(null);
  const [activityState, setActivityState] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState<string>('');
  const [toolActivities, setToolActivities] = useState<ToolActivity[]>([]);
  const [answerBlocks, setAnswerBlocks] = useState<AnswerBlock[]>([]);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [servingModel, setServingModel] = useState<string | null>(null);
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const [limitations, setLimitations] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryTurn[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const [budget, setBudget] = useState<ChatBudget>(EMPTY_BUDGET);
  const chatIdRef = useRef<string | null>(null);
  const activeLevelRef = useRef<ResearchLevel>('low');
  const acceptBudget = useCallback((response: Partial<ChatBudget>) => {
    if (response.chat_id) chatIdRef.current = response.chat_id;
    setBudget(previous => ({ ...previous, ...Object.fromEntries(Object.entries(response).filter(([key, value]) => value !== undefined && ['chat_id', 'tokens_used', 'token_limit', 'usage_estimated', 'chat_exhausted'].includes(key))) }));
  }, []);

  const generation = useRef(0);
  const chatGeneration = useRef(0);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const currentPaperRef = useRef<string | null>(paperId);
  const activeQuestionRef = useRef<string>('');

  // Stable conversation key for persisting and restoring chat history across tab switches
  const documentKey =
    canonicalUrl ||
    (arxivId ? `arxiv_${arxivId}` : null) ||
    (paperId ? `paper_${paperId}` : null);
  const conversationKey = documentKey && (ownerId ? `${ownerId}:${documentKey}` : documentKey);
  const activeKeyRef = useRef<string | null>(null);
  const [loadedConversationKey, setLoadedConversationKey] = useState<string | null>(null);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      ++generation.current;
      isMountedRef.current = false;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Clear transient in-flight state when paperId changes
  useEffect(() => {
    if (currentPaperRef.current !== paperId) {
      ++generation.current;
      currentPaperRef.current = paperId;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      setRunId(null);
      setStatus(null);
      setPolling(false);
      setActiveStep(null);
      setActivityState(null);
      setStreamingText('');
      setToolActivities([]);
      setErrorMessage(null);

      // In environments without chrome.storage (like unit tests), clear chat state on paper change
      if (typeof chrome === 'undefined' || !chrome.storage?.local) {
        setAnswerBlocks([]);
        setEvidence([]);
        setServingModel(null);
        setFallbackReason(null);
        setLimitations(null);
        setHistory([]);
        setMessages([]);
        setBudget(EMPTY_BUDGET); chatIdRef.current = null;
      }

      if (typeof chrome !== 'undefined' && chrome.storage?.session) {
        chrome.storage.session.remove(SESSION_STORAGE_KEY).catch(() => {});
      }
    }
  }, [paperId]);

  // Load and restore saved chat history whenever paper/conversation changes
  useEffect(() => {
    if (activeKeyRef.current !== conversationKey) {
      activeKeyRef.current = conversationKey;
      setBudget(EMPTY_BUDGET); chatIdRef.current = null;
      const restoreEpoch = ++chatGeneration.current;
      setLoadedConversationKey(null);

      if (!conversationKey) {
        setMessages([]);
        setHistory([]);
        setAnswerBlocks([]);
        setEvidence([]);
        setServingModel(null);
        setFallbackReason(null);
        setLimitations(null);
        return;
      }

      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        const storageKey = `paperlens_chat_${conversationKey}`;
        chrome.storage.local
          .get(storageKey)
          .then((data) => {
            if (activeKeyRef.current !== conversationKey || !isMountedRef.current || chatGeneration.current !== restoreEpoch) return;
            setLoadedConversationKey(conversationKey);
            const stored = data[storageKey];
            if (stored && Array.isArray(stored.messages) && stored.messages.length > 0) {
              setMessages(stored.messages);
              if (stored.budget) {
                acceptBudget(stored.budget);
                if (stored.budget.chat_id) client.getChatState(stored.budget.chat_id).then(latest => {
                  if (activeKeyRef.current === conversationKey && chatGeneration.current === restoreEpoch) acceptBudget(latest);
                }).catch(() => {});
              }
              setHistory(stored.history || []);
              setAnswerBlocks(stored.answerBlocks || []);
              setEvidence(stored.evidence || []);
              setServingModel(stored.servingModel || null);
              setFallbackReason(stored.fallbackReason || null);
              setLimitations(stored.limitations || null);
            } else {
              setMessages([]);
              setHistory([]);
              setAnswerBlocks([]);
              setEvidence([]);
              setServingModel(null);
              setFallbackReason(null);
              setLimitations(null);
            }
          })
          .catch(() => {
            if (activeKeyRef.current === conversationKey && isMountedRef.current) {
              setMessages([]);
              setHistory([]);
              setAnswerBlocks([]);
              setEvidence([]);
            }
          });
      }
    }
  }, [conversationKey]);

  // Persist completed / updated conversation to chrome.storage.local
  useEffect(() => {
    if (!conversationKey || activeKeyRef.current !== conversationKey || loadedConversationKey !== conversationKey) return;
    if (messages.length > 0 && typeof chrome !== 'undefined' && chrome.storage?.local) {
      const storageKey = `paperlens_chat_${conversationKey}`;
      chrome.storage.local
        .set({
          [storageKey]: {
            messages,
            history,
            answerBlocks,
            evidence,
            servingModel,
            fallbackReason,
            limitations,
            updatedAt: Date.now(),
            budget,
          },
        })
        .catch(() => {});
    }
  }, [
    conversationKey,
    loadedConversationKey,
    budget,
    messages,
    history,
    answerBlocks,
    evidence,
    servingModel,
    fallbackReason,
    limitations,
  ]);

  // Session storage restoration on mount
  useEffect(() => {
    if (!paperId) return;
    const epoch = generation.current;

    if (typeof chrome !== 'undefined' && chrome.storage?.session) {
      chrome.storage.session
        .get(SESSION_STORAGE_KEY)
        .then((data) => {
          if (generation.current !== epoch || !isMountedRef.current) return;
          const stored = data[SESSION_STORAGE_KEY];
          if (
            stored &&
            stored.paperId === paperId &&
            stored.runId &&
            ['queued', 'running'].includes(stored.status)
          ) {
            setRunId(stored.runId);
            setStatus(stored.status);
            pollRun(stored.runId);
          }
        })
        .catch(() => {});
    }
  }, [paperId]);

  const updateSessionStorage = useCallback(
    (newRunId: string | null, newStatus: string | null) => {
      if (typeof chrome !== 'undefined' && chrome.storage?.session) {
        if (
          !newRunId ||
          ['completed', 'partial', 'evidence_only', 'cancelled', 'failed', 'refused'].includes(
            newStatus || ''
          )
        ) {
          chrome.storage.session.remove(SESSION_STORAGE_KEY).catch(() => {});
        } else {
          chrome.storage.session
            .set({
              [SESSION_STORAGE_KEY]: {
                runId: newRunId,
                paperId,
                arxivId,
                version,
                status: newStatus,
              },
            })
            .catch(() => {});
        }
      }
    },
    [paperId, arxivId, version]
  );

  const pollRun = useCallback(
    async (targetRunId: string) => {
      const epoch = generation.current;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }

      setPolling(true);

      const check = async () => {
        if (!isMountedRef.current || generation.current !== epoch) return;

        try {
          const res = await client.getAgentRun(targetRunId);
          if (!isMountedRef.current || generation.current !== epoch) return;

          acceptBudget(res);
          setStatus(res.status);
          setServingModel(res.serving_model || null);
          setFallbackReason(res.fallback_reason || null);
          setLimitations(res.limitations || null);
          setErrorMessage(res.error_message || null);

          if (res.evidence && res.evidence.length > 0) {
            setEvidence(res.evidence);
          }

          if (res.answer_blocks && res.answer_blocks.length > 0) {
            setAnswerBlocks(res.answer_blocks);
          }

          const terminal = [
            'completed',
            'partial',
            'evidence_only',
            'cancelled',
            'failed',
            'refused',
          ].includes(res.status);

          if (terminal) {
            setPolling(false);
            setActiveStep(null);
            setActivityState(null);
            updateSessionStorage(targetRunId, res.status);

            const answerText =
              res.answer_blocks?.map((b) => b.text).join('\n\n') || '';

            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  status: res.status,
                  content: answerText || last.content,
                  answerBlocks: res.answer_blocks || [],
                  followUps: res.follow_ups || [],
                  evidence: res.evidence || last.evidence || [],
                  servingModel: res.serving_model || null,
                  fallbackReason: res.fallback_reason || null,
                  limitations: res.limitations || null,
                  error: res.error_message || null,
                  isStreaming: false,
                };
              }
              return updated;
            });

            // Record into conversational history if an answer was produced
            if (['completed', 'partial'].includes(res.status) && res.answer_blocks?.length) {
              setHistory((prev) => {
                const updated = [...prev];
                if (activeQuestionRef.current) {
                  updated.push({ role: 'user', content: activeQuestionRef.current });
                }
                updated.push({ role: 'assistant', content: answerText });
                return updated.slice(-MAX_HISTORY_TURNS);
              });
            }
            return;
          }

          // In-progress status descriptions
          if (res.status === 'queued') {
            setActiveStep('Queued for processing...');
            setActivityState('Queued for processing...');
          } else if (res.status === 'running') {
            setActiveStep('Searching evidence and analyzing sections...');
            setActivityState('Searching evidence and analyzing sections...');
          }

          updateSessionStorage(targetRunId, res.status);
          pollTimerRef.current = setTimeout(check, pollIntervalMs);
        } catch (err) {
          if (!isMountedRef.current || generation.current !== epoch) return;
          setPolling(false);
          setActiveStep(null);
          setActivityState(null);
          setErrorMessage((err as Error).message);
          setStatus('failed');
          updateSessionStorage(targetRunId, 'failed');
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant') {
              updated[updated.length - 1] = {
                ...last,
                status: 'failed',
                error: (err as Error).message,
                isStreaming: false,
              };
            }
            return updated;
          });
        }
      };

      await check();
    },
    [client, pollIntervalMs, updateSessionStorage]
  );

  const startRun = useCallback(
    async (
      questionText: string,
      mode: string = 'A2',
      attachments?: ComposerAttachment[],
      overridePaperId?: string,
      level: ResearchLevel = 'low'
    ) => {
      const targetPaperId = overridePaperId || paperId;
      if (budget.chat_exhausted) return;
      activeLevelRef.current = level;
      ++chatGeneration.current;
      setLoadedConversationKey(conversationKey);
      if (!targetPaperId || !questionText.trim()) return;
      const epoch = ++generation.current;

      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }

      const trimmedQuestion = questionText.trim();
      activeQuestionRef.current = trimmedQuestion;
      setAnswerBlocks([]);
      setEvidence([]);
      setServingModel(null);
      setRunId(null);
      setErrorMessage(null);
      setFallbackReason(null);
      setLimitations(null);
      setStreamingText('');
      setToolActivities([]);
      setActiveStep('Initiating agent run...');
      setActivityState('Searching the paper...');
      setPolling(true);

      // Append user message with attachments and new in-flight assistant message
      const userMsgId = `u_${Date.now()}`;
      const asstMsgId = `a_${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        {
          id: userMsgId,
          role: 'user',
          content: trimmedQuestion,
          attachments: attachments && attachments.length > 0 ? attachments : undefined,
          timestamp: Date.now(),
        },
        {
          id: asstMsgId,
          role: 'assistant',
          content: '',
          timestamp: Date.now(),
          status: 'queued',
          activityState: 'Searching the paper...',
          toolActivities: [],
          isStreaming: true,
        },
      ]);

      const requestId = `req_agent_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const abortCtrl = new AbortController();
      abortControllerRef.current = abortCtrl;

      // Keep the latest research image available for visual follow-up questions.
      const refersToImage = /image|figure|diagram|chart|plot|hình|ảnh|sơ đồ|biểu đồ|that same|hình trên/i.test(trimmedQuestion);
      const imageContext = attachments?.length ? attachments : refersToImage ? [...messages].reverse().find(message => message.role === 'user' && message.attachments?.some(image => image.dataUrl))?.attachments : undefined;
      try {
        const res = await client.createAgentRun({
          request_id: requestId,
          paper_id: targetPaperId,
          question: trimmedQuestion,
          chat_id: chatIdRef.current || undefined,
          level,
          images: (imageContext || []).filter(image => image.dataUrl).map(image => ({ name: image.name, data_url: image.dataUrl! })),
          history: history.slice(-MAX_HISTORY_TURNS).map((turn) => ({ ...turn, content: turn.content.slice(0, 4096) })),
          mode,
        });

        if (!isMountedRef.current || generation.current !== epoch) {
          client.cancelAgentRun(res.run_id).catch(() => {});
          return;
        }

        acceptBudget(res);
        setRunId(res.run_id);
        setStatus(res.status);
        updateSessionStorage(res.run_id, res.status);

        if (['completed', 'partial', 'evidence_only', 'cancelled', 'failed', 'refused'].includes(res.status)) {
          setPolling(false);
          setActiveStep(null);
          setActivityState(null);
          if (res.answer_blocks) setAnswerBlocks(res.answer_blocks);
          if (res.evidence) setEvidence(res.evidence);
          setServingModel(res.serving_model || null);
          setFallbackReason(res.fallback_reason || null);
          setLimitations(res.limitations || null);

          const answerText =
            res.answer_blocks?.map((b) => b.text).join('\n\n') || '';

          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant') {
              updated[updated.length - 1] = {
                ...last,
                status: res.status,
                content: answerText || last.content,
                answerBlocks: res.answer_blocks || [],
                followUps: res.follow_ups || [],
                evidence: res.evidence || [],
                servingModel: res.serving_model || null,
                fallbackReason: res.fallback_reason || null,
                limitations: res.limitations || null,
                isStreaming: false,
              };
            }
            return updated;
          });

          // Record into conversational history if an answer was produced
          if (['completed', 'partial'].includes(res.status) && res.answer_blocks?.length) {
            setHistory((prev) => {
              const updated = [...prev];
              if (activeQuestionRef.current) {
                updated.push({ role: 'user', content: activeQuestionRef.current });
              }
              updated.push({ role: 'assistant', content: answerText });
              return updated.slice(-MAX_HISTORY_TURNS);
            });
          }
          return;
        }

        // Connect to genuine streaming events
        let streamEnded = false;
        try {
          await client.streamAgentRunEvents(
            res.run_id,
            (ev: AgentRunEvent) => {
              if (!isMountedRef.current || generation.current !== epoch) return;

              if (ev.type === 'activity' && ev.message) {
                setActiveStep(ev.message);
                setActivityState(ev.message);
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...last,
                      activityState: ev.message,
                    };
                  }
                  return updated;
                });
              } else if (ev.type === 'tool_call') {
                const item: ToolActivity = {
                  id: `tool_${Date.now()}_${Math.random().toString(36).slice(2, 5)}`,
                  toolName: ev.tool_name || 'tool',
                  state: 'running',
                  arguments: ev.arguments,
                };
                setToolActivities((prev) => [...prev, item]);
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...last,
                      toolActivities: [...(last.toolActivities || []), item],
                    };
                  }
                  return updated;
                });
              } else if (ev.type === 'tool_result') {
                setToolActivities((prev) => {
                  const updated = [...prev];
                  const idx = findLastIndex(updated, (t: ToolActivity) => t.toolName === ev.tool_name);
                  if (idx >= 0) {
                    updated[idx] = {
                      ...updated[idx],
                      state: 'completed',
                      summary: ev.summary,
                      count: ev.count,
                    };
                  }
                  return updated;
                });
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === 'assistant' && last.toolActivities) {
                    const tools = [...last.toolActivities];
                    const idx = findLastIndex(tools, (t: ToolActivity) => t.toolName === ev.tool_name);
                    if (idx >= 0) {
                      tools[idx] = {
                        ...tools[idx],
                        state: 'completed',
                        summary: ev.summary,
                        count: ev.count,
                      };
                      updated[updated.length - 1] = {
                        ...last,
                        toolActivities: tools,
                      };
                    }
                  }
                  return updated;
                });
              } else if (ev.type === 'delta') {
                const currentText = ev.text !== undefined ? ev.text : '';
                if (currentText) {
                  setStreamingText(currentText);
                  setMessages((prev) => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === 'assistant') {
                      updated[updated.length - 1] = {
                        ...last,
                        content: currentText,
                      };
                    }
                    return updated;
                  });
                }
              } else if (ev.type === 'done') {
                acceptBudget(ev);
                streamEnded = true;
                setPolling(false);
                setActiveStep(null);
                setActivityState(null);
                if (ev.status) setStatus(ev.status);
                if (ev.answer_blocks) setAnswerBlocks(ev.answer_blocks);
                if (ev.evidence) setEvidence(ev.evidence);
                setServingModel(ev.serving_model || null);
                setFallbackReason(ev.fallback_reason || null);
                setLimitations(ev.limitations || null);

                const finalAnsText =
                  ev.answer_blocks?.map((b) => b.text).join('\n\n') || streamingText;

                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...last,
                      status: ev.status,
                      content: finalAnsText || last.content,
                      answerBlocks: ev.answer_blocks || [],
                      followUps: ev.follow_ups || [],
                      evidence: ev.evidence || [],
                      servingModel: ev.serving_model || null,
                      fallbackReason: ev.fallback_reason || null,
                      limitations: ev.limitations || null,
                      isStreaming: false,
                    };
                  }
                  return updated;
                });

                if (['completed', 'partial'].includes(ev.status || '') && ev.answer_blocks?.length) {
                  setHistory((prev) => {
                    const updated = [...prev];
                    if (activeQuestionRef.current) {
                      updated.push({ role: 'user', content: activeQuestionRef.current });
                    }
                    updated.push({ role: 'assistant', content: finalAnsText });
                    return updated.slice(-MAX_HISTORY_TURNS);
                  });
                }
                updateSessionStorage(res.run_id, ev.status || 'completed');
              } else if (ev.type === 'error') {
                acceptBudget(ev);
                streamEnded = true;
                setPolling(false);
                setActiveStep(null);
                setActivityState(null);
                setStatus('failed');
                setErrorMessage(ev.error || 'Execution error');
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...last,
                      status: 'failed',
                      error: ev.error || 'Execution error',
                      isStreaming: false,
                    };
                  }
                  return updated;
                });
                updateSessionStorage(res.run_id, 'failed');
              }
            },
            abortCtrl.signal
          );
        } catch {
          // Streaming connection threw or was rejected
        }

        if (!streamEnded && generation.current === epoch && isMountedRef.current) {
          pollRun(res.run_id);
        }
      } catch (err) {
        if (!isMountedRef.current || generation.current !== epoch) return;
        setPolling(false);
        setActiveStep(null);
        setActivityState(null);
        setErrorMessage((err as Error).message);
        setStatus('failed');
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === 'assistant') {
            updated[updated.length - 1] = {
              ...last,
              status: 'failed',
              error: (err as Error).message,
              isStreaming: false,
            };
          }
          return updated;
        });
      }
    },
    [paperId, history, client, updateSessionStorage, pollRun, streamingText, acceptBudget, budget.chat_exhausted, messages, conversationKey]
  );

  const cancelRun = useCallback(async () => {
    const epoch = ++generation.current;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setPolling(false);
    setActiveStep(null);
    setActivityState(null);
    setStatus('cancelled');

    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (last && last.role === 'assistant' && last.isStreaming) {
        updated[updated.length - 1] = {
          ...last,
          status: 'cancelled',
          isStreaming: false,
        };
      }
      return updated;
    });

    if (!runId) return;

    try {
      const res = await client.cancelAgentRun(runId);
      if (generation.current === epoch) { setStatus(res.status); acceptBudget(res); }
    } catch {
      if (generation.current === epoch) setStatus('cancelled');
    } finally {
      if (generation.current !== epoch) return;
      setPolling(false);
      setActiveStep(null);
      setActivityState(null);
      updateSessionStorage(runId, 'cancelled');
    }
  }, [runId, client, updateSessionStorage]);

  const resetConversation = useCallback(() => {
    ++generation.current;
    ++chatGeneration.current;
    setLoadedConversationKey(conversationKey);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setBudget(EMPTY_BUDGET); chatIdRef.current = null;
    setRunId(null);
    setStatus(null);
    setPolling(false);
    setActiveStep(null);
    setActivityState(null);
    setStreamingText('');
    setToolActivities([]);
    setAnswerBlocks([]);
    setEvidence([]);
    setServingModel(null);
    setFallbackReason(null);
    setLimitations(null);
    setErrorMessage(null);
    setHistory([]);
    setMessages([]);
    activeQuestionRef.current = '';

    if (typeof chrome !== 'undefined') {
      if (chrome.storage?.session) {
        chrome.storage.session.remove(SESSION_STORAGE_KEY).catch(() => {});
      }
      if (chrome.storage?.local && conversationKey) {
        chrome.storage.local.remove(`paperlens_chat_${conversationKey}`).catch(() => {});
      }
    }
  }, [conversationKey]);

  const retryLastTurn = useCallback(async () => {
    if (activeQuestionRef.current) {
      const q = activeQuestionRef.current;
      setMessages((prev) => {
        // Drop trailing failed assistant message and the user question so it re-adds cleanly
        if (prev.length >= 2 && prev[prev.length - 1].role === 'assistant' && prev[prev.length - 2].role === 'user') {
          return prev.slice(0, -2);
        }
        return prev;
      });
      await startRun(q, 'A2', undefined, undefined, activeLevelRef.current);
    }
  }, [startRun]);

  const restoreConversation = useCallback((saved: SavedConversation) => {
    resetConversation();
    const last = saved.messages.filter(message => message.role === 'assistant').at(-1);
    setMessages(saved.messages);
    const completedMessages=saved.active_run_id ? saved.messages.slice(0,-2) : saved.messages;
    setHistory(completedMessages.map(message => ({role:message.role,content:message.role === 'assistant'
      ? (message.answerBlocks || []).map(block => block.text).join('\n\n') : message.content}))
      .filter(turn => turn.content.trim()).slice(-MAX_HISTORY_TURNS));
    acceptBudget(saved.budget);
    setAnswerBlocks(last?.answerBlocks || []); setEvidence(last?.evidence || []);
    setStatus(last?.status || null); setServingModel(last?.servingModel || null);
    setLimitations(last?.limitations || null);
    activeQuestionRef.current = saved.messages.filter(message=>message.role==='user').at(-1)?.content || '';
    if(saved.active_run_id){setRunId(saved.active_run_id);setPolling(true);void pollRun(saved.active_run_id);}
  }, [resetConversation,acceptBudget,pollRun]);

  return {
    budget,
    runId,
    status,
    polling,
    activeStep,
    answerBlocks,
    evidence,
    servingModel,
    fallbackReason,
    limitations,
    errorMessage,
    history,
    messages,
    streamingText,
    toolActivities,
    activityState,
    startRun,
    cancelRun,
    resetConversation,
    retryLastTurn,
    restoreConversation,
  };
}
