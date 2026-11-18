# PaperLens Evaluation Artifacts

Each QASPER run has a directory keyed by `run_id` and a manifest that records the dataset revision and checksum, split, sample IDs, configuration, and prompt, tool, and model versions. Store retrieval results, valid traces, usage, and metric outputs under the corresponding identifiers. Mark each run as live or replay in the manifest.

Replay uses saved benchmark evidence with suitable usage rights. Shared artifacts include checksums, instructions for obtaining the data, and the status of each record. User data stays under the product namespace and follows the backend retention rules.
