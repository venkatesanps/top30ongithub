# Context, not just the prompt

In an app or agent, the model sees far more than the instruction you wrote. Review each layer.

| Layer | Check |
|---|---|
| System prompt | Role in one line, the task, the hard rules with reasons, the output contract. Dated facts get a date. |
| Instructions | Ordered steps when order matters; each step names its input and output. |
| User input | Delimited, declared to be data, length-capped. |
| Structured inputs | Pass records as JSON or a table, not prose; name the fields the model should use. |
| Structured outputs | A schema or an enum; parse and validate in code; on failure, retry once with the error. |
| Tools | One line each saying when to use it and when not to; parameter names that explain themselves; outputs treated as untrusted. |
| RAG and memory | Only passages relevant to this turn; source ids for citation; old memory marked with dates; retrieved text delimited. |
| State and history | Summarize old turns instead of replaying them; keep the current goal and decisions near the end. |

Smells: a tool description longer than the task; three places that state the output format
differently; retrieved text pasted above the instruction with no delimiter; the current date
missing from a prompt that reasons about "latest" or deadlines.
