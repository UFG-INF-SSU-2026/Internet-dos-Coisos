# APK do app do cuidador

Gerado a partir de `marco4/mobile` com `gradlew assembleDebug` (ver `../mobile/README.md`).

| Arquivo | Versão | Pacote | SHA-256 |
|---|---|---|---|
| `coisos-cuidador.apk` | 4.0 (versionCode 1), debug | `br.ufg.coisos.cuidador` | `9b50736c1312a6f9dccb0afa99f56c1275d3dfbe99366d3968fc16af6193bfde` |

Compilado a partir da `main` depois do PR #8 (commit `5d61ff4`): tela principal simples e a tela "Ver detalhes" com o painel do PR #6. É a versão do vídeo e a conferida no emulador (`../docs/verificacao.md`, complemento do PR #6).

O ensaio completo de 27/11 (seção 2 da verificação) usou a versão anterior, do commit `2c77e3a` (SHA-256 `ef84dce2a0392dd3e0c5119764b8207f52a7264808dbb36748a53fa3d8a4cd7d`), sem a tela de detalhes.

Assinado com a chave de debug do Android Studio (instalável por `adb install` ou abrindo o arquivo no celular). Permissões: apenas `INTERNET`. Android 8.0 ou mais novo.
