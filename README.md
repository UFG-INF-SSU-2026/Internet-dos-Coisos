# Internet dos Coisos

**Software para Sistemas Ubíquos — UFG / Instituto de Informática (2026/2)**

Projeto acadêmico: protótipo de monitoramento de sinais vitais de pessoas em situação de vulnerabilidade física por *smart clothing*, usando ESP32/Wokwi, processamento local, comunicação de eventos e consulta por cuidador.

## Integrantes

- Felipe Alves — 202105026
- Felipe O Carvalho — 202011561
- Matheus Augusto — 202305532
- Murilo Bernardo — 202203524

## Entregas do grupo

| Entrega | Propósito | Documentação |
|---|---|---|
| Atividade 01 | Problema, atores, contexto e arquitetura conceitual | [atividade-01.md](atividade-01.md) |
| Atividade 02 | Eventos, processamento temporal e responsabilidades | [atividade-02.md](atividade-02.md) |
| Marco 2 | Protótipo integrado ESP32 → MQTT → consumidor Python | [marco2/README.md](marco2/README.md) |
| **Marco 3 (versão atual)** | **HTTP/REST, autenticação do dispositivo, login do cuidador, autorização e painel web** | **[marco3/README.md](marco3/README.md)** |

## Como funciona a versão atual (Marco 3)

```text
ESP32 (Wokwi gratuito / Arduino C++)
  ├─ sensores simulados e janelas temporais
  ├─ decide NORMAL / ATENCAO / DADOS_INSUFICIENTES
  ├─ aciona um LED e o buzzer localmente
  └─ HTTPS POST + chave de dispositivo
           |
           v
    Túnel gratuito da Cloudflare (https://xxxx.trycloudflare.com)
           |
           v
    API REST em Python (FastAPI), no PC do grupo
      ├─ valida chave e vínculo dispositivo/paciente
      ├─ valida contrato JSON, deduplicação e sequência
      └─ restringe consulta por sessão do cuidador
           ^
           | HTTP GET (login/sessão)
           v
      Painel HTML do cuidador
```

A comunicação principal do Marco 3 é **HTTP/REST (sobre HTTPS)**. A versão MQTT do Marco 2 permanece no histórico, mas não precisa ser executada ao demonstrar o Marco 3. **Não usamos Neon nem banco de dados**: os dados ficam em memória porque o objetivo é compreender comunicação, identificação e acesso.

### Executar rapidamente

1. Abra o terminal na pasta `marco3/api`.
2. Rode `python -m pip install -r requirements.txt`.
3. Rode `python gerar_config.py` para criar chaves e senha da demo.
4. Rode `python app.py` e entre em [http://127.0.0.1:5000/login](http://127.0.0.1:5000/login).
5. Em outro terminal, rode `cloudflared tunnel --url http://127.0.0.1:5000` (gratuito, sem conta) e copie a URL `https://...trycloudflare.com`.
6. Use os arquivos de `marco3/produtor` no Wokwi gratuito e cole essa URL no `config.h`.

**Siga o [guia completo do Marco 3](marco3/README.md)** para instalar o túnel, configurar `config.h`, fazer a demonstração, entender login/autorização, testar o projeto e preparar a apresentação.

> **Limitação:** simulação didática sem validade clínica. Tudo é gratuito: o ESP32 roda no Wokwi e a API no terminal do PC, ligados por um túnel HTTPS temporário da Cloudflare.

## Uso de ferramentas de IA

Utilizamos ferramentas de IA generativa como apoio na revisão do código e da documentação, conforme o [Guia de Integridade Acadêmica da UFG](https://ufg.br/n/185267-nova-versao-do-guia-de-integridade-academica-traz-capitulo-sobre-ia). As decisões de projeto, a implementação e os testes foram conferidos pelo grupo, e todos os integrantes sabem explicar o funcionamento do sistema.
