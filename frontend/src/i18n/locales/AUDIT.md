# Frontend i18n audit

`MISSING` = absent or empty. `ECHOED` = present, non-empty, and still the
English source — which a completeness check cannot see, because English is
both present and non-empty.

| locale | keys | missing | echoed |
|---|---:|---:|---:|
| vi | 945 | 7 | 0 |
| ja | 945 | 7 | 4 |
| ko | 945 | 7 | 4 |
| zh-CN | 945 | 7 | 3 |
| zh-TW | 945 | 7 | 3 |
| es | 945 | 7 | 0 |
| pt-BR | 945 | 7 | 0 |
| fr | 945 | 7 | 0 |
| de | 945 | 7 | 1 |
| ru | 945 | 7 | 3 |
| id | 945 | 7 | 0 |
| ms | 945 | 7 | 0 |
| tr | 945 | 7 | 0 |
| ar | 945 | 7 | 2 |
| hi | 945 | 7 | 4 |
| bn | 945 | 7 | 4 |
| th | 945 | 7 | 5 |

**0/17 locales clean.**

### vi
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### ja
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.model_modal.add.ctx
  - `ECHOED` settings.model_modal.edit.verify_ok
  - `ECHOED` settings.providers.add_dialog.api_key_ph
  - `ECHOED` settings.providers.edit_dialog.api_key_ph
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### ko
  - `ECHOED` chat.context_panel.tok
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.model_modal.add.ctx
  - `ECHOED` settings.providers.add_dialog.api_key_ph
  - `ECHOED` settings.providers.edit_dialog.api_key_ph
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### zh-CN
  - `ECHOED` chat.context_panel.tok
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.providers.add_dialog.api_key_ph
  - `ECHOED` settings.providers.edit_dialog.api_key_ph
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### zh-TW
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.model_modal.add.ctx
  - `ECHOED` settings.providers.add_dialog.api_key_ph
  - `ECHOED` settings.providers.edit_dialog.api_key_ph
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### es
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### pt-BR
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### fr
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### de
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.model_modal.edit.pricing_suggestion_found
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### ru
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.model_modal.add.ctx
  - `ECHOED` settings.providers.add_dialog.api_key_ph
  - `ECHOED` settings.providers.edit_dialog.api_key_ph
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### id
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### ms
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### tr
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### ar
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.providers.add_dialog.api_key_ph
  - `ECHOED` settings.providers.edit_dialog.api_key_ph
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### hi
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.model_modal.add.ctx
  - `ECHOED` settings.providers.add_dialog.api_key_ph
  - `ECHOED` settings.providers.edit_dialog.api_key_ph
  - `ECHOED` settings.providers.toast.verify_ok
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### bn
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.model_modal.add.ctx
  - `ECHOED` settings.providers.add_dialog.api_key_ph
  - `ECHOED` settings.providers.edit_dialog.api_key_ph
  - `ECHOED` settings.providers.toast.verify_ok
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

### th
  - `ECHOED` chat.inspector.title
  - `MISSING` chat: 5 (e.g. ['disambiguation.cancel', 'disambiguation.empty', 'disambiguation.label'])
  - `ECHOED` settings.model_modal.add.ctx
  - `ECHOED` settings.providers.add_dialog.api_key_ph
  - `ECHOED` settings.providers.edit_dialog.api_key_ph
  - `ECHOED` settings.services.add_dialog.key_ph
  - `MISSING` settings: 2 (e.g. ['defaultModels.composer', 'defaultModels.composerHint'])

