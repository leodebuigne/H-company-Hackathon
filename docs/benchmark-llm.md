# Benchmark des modèles de langage (`parse_intent`)

20 phrases de `docs/test-phrases.md`, date du jour `2026-11-18`, Hugging Face Inference Providers, température 0. Une réponse est bonne si elle passe le schéma `Intent` et que tous les champs attendus sont exacts. Objectif : 18 sur 20.

**Attention : le prompt a été réglé en regardant ces mêmes 20 phrases, le score est donc optimiste.** À confirmer sur des phrases nouvelles avant la démo. `missing` et `question` sont calculés en code (règles du plan), pas par le modèle.

| Modèle | Bonnes réponses | Temps médian | Temps max | Jetons par phrase |
| --- | --- | --- | --- | --- |
| `meta-llama/Llama-3.3-70B-Instruct` | 20 / 20 | 1.3 s | 5.5 s | 1259 |
| `google/gemma-4-31B-it` | 20 / 20 | 1.9 s | 4.8 s | 1239 |
| `openai/gpt-oss-120b` | 19 / 20 | 1.9 s | 7.7 s | 1617 |
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | 13 / 20 | 3.7 s | 7.5 s | 1285 |

## Écarts

### `meta-llama/Llama-3.3-70B-Instruct`
Aucun.

### `google/gemma-4-31B-it`
Aucun.

### `openai/gpt-oss-120b`
- Phrase 17 : not_understood : intention illisible : 1 validation error for Intent
kind
  Input should be 'new_request', 'refine', 'choose', 'details', 'confirm', 'deny', 'cancel' or 'other' [type=literal_error, input_value=None, input_type=NoneType]
    For further information visit https://errors.pydantic.dev/2.14/v/literal_error

### `Qwen/Qwen3-30B-A3B-Instruct-2507`
- Phrase 1 : details.destination : attendu 'Lille', reçu None ; missing : attendu ['details.origin'], reçu ['details.origin', 'details.destination']
- Phrase 2 : details.origin : attendu 'Paris', reçu None ; details.destination : attendu 'Lyon', reçu None ; missing : attendu [], reçu ['details.origin', 'details.destination']
- Phrase 3 : details.origin : attendu 'Bordeaux', reçu None ; details.destination : attendu 'Toulouse', reçu None ; missing : attendu [], reçu ['details.origin', 'details.destination']
- Phrase 4 : details.destination : attendu 'Marseille', reçu None ; missing : attendu ['details.origin', 'when.date'], reçu ['details.origin', 'details.destination', 'when.date']
- Phrase 5 : when.after : attendu '18:00', reçu None ; details.origin : attendu 'Paris', reçu None ; details.destination : attendu 'Nantes', reçu None ; missing : attendu [], reçu ['details.origin', 'details.destination']
- Phrase 7 : details.origin : attendu 'Paris', reçu None ; details.destination : attendu 'Lyon', reçu None ; missing : attendu [], reçu ['details.origin', 'details.destination']
- Phrase 11 : details.cuisine~ : attendu 'tha', reçu None

Le prix par jeton dépend du fournisseur que Hugging Face choisit : voir le tableau de bord Inference Providers de votre compte pour le coût réel.
