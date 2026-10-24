# Token usage and cost — final full-dataset run

The run that produced the submitted `output.csv` (`python code/main.py`, 518 requests) is
fully deterministic and **does not call any language model**. Intent, identity resolution,
evidence parsing, state reconstruction, policy and planning are all code.

## Final run totals

| Provider | Model | Model calls | Input tokens | Output tokens | Total tokens | Avg tokens / request | Est. cost | Est. cost / request |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| — (none) | — | 0 | 0 | 0 | 0 | 0 | $0.00 | $0.00 |
| **Overall** | | **0** | **0** | **0** | **0** | **0** | **$0.00** | **$0.00** |

* Requests processed: 518 (508 deletion audits, 10 NOT_APPLICABLE).
* Wall-clock: about 1 s on a laptop (Python 3.12, standard library only).
* No API keys or network access are needed.

## Development-time model use (not part of the final run)

* **Anthropic Claude (`claude-opus-5-5`) via Claude Code** was the coding assistant. It also
  transcribed the 11 PNG screenshots under `dataset/evidence/images/` into structured facts,
  which are cached in `code/audit/media_extractions.py`. The 4 PDFs were read with
  `pdftotext`, not with a model.
* That work happened inside the interactive coding session. Its tokens are not metered per
  call by the pipeline and are not part of the submitted run, so no per-call figures are
  reported here rather than estimated.
* Because the cache is committed, re-running the pipeline costs nothing and gives identical
  results.
