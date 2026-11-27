#pragma once
// Exemplo de formato. NAO use a chave abaixo em uma apresentacao real.
// Gere config.h e api/.env com o mesmo segredo: python marco4/api/gerar_config.py
// API_BASE_URL: no Wokwi do VS Code, o gateway local alcanca a API desta maquina (D33).
// O tunel trycloudflare redireciona http:// para https:// (301), e o sketch nao completa
// HTTPS (D17); as mensagens vao assinadas com a chave.
const char* API_BASE_URL = "http://host.wokwi.internal:5000";
const char* DEVICE_API_KEY = "EXEMPLO_SUBSTITUIR_PELA_CHAVE_GERADA";
