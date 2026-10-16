#pragma once
// Configuracao do ESP32 (versionada de proposito: chave FIXA de demonstracao, decisao D11).
// A mesma chave fica em api/.env, criado por: python marco3/api/gerar_config.py
// A cada demonstracao, troque so a URL pela que o comando
// "cloudflared tunnel --url http://127.0.0.1:5000" mostrar, usando http://
// (o Wokwi nao completa HTTPS; as mensagens vao assinadas com a chave, decisao D17).
const char* API_BASE_URL = "http://COLE-AQUI-A-URL-DO-TUNEL.trycloudflare.com";
const char* DEVICE_API_KEY = "lzseXbbE_7KGHTYSrPypIxwwbfvxihAMXLjnZ8Nhhsg";
