#pragma once
// Exemplo de formato. NAO use a chave abaixo em uma apresentacao real.
// Gere config.h e api/.env com o mesmo segredo: python marco3/api/gerar_config.py
// API_BASE_URL: URL do tunel gratuito da Cloudflare, com http:// (o Wokwi nao completa HTTPS;
// as mensagens vao assinadas com a chave, decisao D17).
const char* API_BASE_URL = "http://COLE-AQUI-A-URL-DO-TUNEL.trycloudflare.com";
const char* DEVICE_API_KEY = "EXEMPLO_SUBSTITUIR_PELA_CHAVE_GERADA";
