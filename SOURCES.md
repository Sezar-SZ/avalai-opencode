# Official integration references 📚

The helper's integration behavior is based only on official AvalAI and OpenCode documentation.

## AvalAI

- **Authentication** — API keys and the recommended `Authorization: Bearer` header  
  https://docs.avalai.ir/en/api-reference/authentication

- **Models API** — authenticated `GET /v1/models`, `mode`, `max_input_tokens`, `max_output_tokens`, pricing, and function-calling metadata  
  https://docs.avalai.ir/en/api-reference/models

- **Official API routes** — `api.avalai.ir`, `api.avalapis.ir`, and `api.avalai.org`; same API keys and API surface  
  https://docs.avalai.ir/en/news/2025-06-15-expanded-api-access-domains

## OpenCode

- **Configuration** — global config location, JSON/JSONC support, config merging, and `{env:VARIABLE_NAME}` substitution  
  https://opencode.ai/docs/config/

- **Custom providers** — `@ai-sdk/openai-compatible`, `baseURL`, `apiKey`, model maps, model costs, and model limits  
  https://opencode.ai/docs/providers/

- **Current config schema** — exact supported provider and model fields  
  https://opencode.ai/config.json
