#!/usr/bin/env python3
"""
MARCO 2 - CONSUMIDOR
Software para Sistemas Ubiquos - UFG / INF

Assina o topico publicado pelo produtor (ESP32/Wokwi), valida o evento
recebido e produz efeito observavel: log estruturado e mudanca de estado
na tela.

Responsabilidades deste componente:
  - validar o contrato (schemaVersion e campos obrigatorios);
  - detectar duplicata, salto e chegada fora de ordem pelo campo sequence;
  - tornar visivel o estado atual do paciente e a disponibilidade do
    dispositivo (via last will publicada pelo broker).

Uso:
    pip install paho-mqtt
    python consumidor.py
"""

import json
import sys
from datetime import datetime

import paho.mqtt.client as mqtt

# --- configuracao ---------------------------------------------------------
BROKER = "broker.hivemq.com"
PORTA = 1883

# Precisa ser o MESMO prefixo configurado no produtor.
BASE = "ufg/ssu/2026-2/internet-das-coisos/patient-0042"
TOPICO_STATE = f"{BASE}/state"
TOPICO_STATUS = f"{BASE}/status"

SCHEMA_SUPORTADO = 1
CAMPOS_OBRIGATORIOS = ["schemaVersion", "eventType", "eventId",
                       "deviceId", "entityId", "sequence", "state"]

# --- estado do consumidor -------------------------------------------------
ultima_sequencia = None
ids_processados = set()
estado_atual = "?"
dispositivo = "?"
recebidos = descartados = 0

CORES = {
    "NORMAL": "\033[32m",
    "ATENCAO": "\033[31m",
    "DADOS_INSUFICIENTES": "\033[34m",
    "DESCONHECIDO": "\033[90m",
}
RESET = "\033[0m"


def agora() -> str:
    return datetime.now().strftime("%H:%M:%S")


def painel() -> None:
    """Efeito observavel: estado corrente do paciente e do dispositivo."""
    cor = CORES.get(estado_atual, "")
    print()
    print("  +----------------------------------------------+")
    print(f"  |  PACIENTE    {cor}{estado_atual:<32}{RESET}|")
    print(f"  |  DISPOSITIVO {dispositivo:<32}|")
    print(f"  |  eventos: {recebidos:<4} descartados: {descartados:<16}|")
    print("  +----------------------------------------------+")
    print()


def validar(evento: dict) -> str | None:
    """Devolve o motivo da rejeicao, ou None se o evento for aceitavel."""
    faltando = [c for c in CAMPOS_OBRIGATORIOS if c not in evento]
    if faltando:
        return f"campos ausentes: {', '.join(faltando)}"
    if evento["schemaVersion"] != SCHEMA_SUPORTADO:
        return (f"schemaVersion {evento['schemaVersion']} nao suportado "
                f"(este consumidor entende a versao {SCHEMA_SUPORTADO})")
    if evento["eventId"] in ids_processados:
        return f"duplicado: eventId {evento['eventId']} ja processado"
    return None


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        client.subscribe([(TOPICO_STATE, 1), (TOPICO_STATUS, 1)])
        print(f"[{agora()}] conectado a {BROKER}")
        print(f"[{agora()}] assinando  {TOPICO_STATE}")
        print(f"[{agora()}] assinando  {TOPICO_STATUS}")
        print(f"[{agora()}] aguardando eventos...\n")
    else:
        print(f"[{agora()}] falha na conexao (rc={rc})")


def on_disconnect(client, userdata, rc, properties=None):
    print(f"[{agora()}] desconectado do broker (rc={rc}) - tentando reconectar")


def on_message(client, userdata, msg):
    global ultima_sequencia, estado_atual, dispositivo, recebidos, descartados

    bruto = msg.payload.decode("utf-8", errors="replace")

    # Topico de status: publicado pelo dispositivo ou pelo broker (last will).
    if msg.topic == TOPICO_STATUS:
        try:
            dispositivo = json.loads(bruto).get("status", "?")
        except json.JSONDecodeError:
            dispositivo = bruto
        marca = "ONLINE" if dispositivo == "online" else "OFFLINE (last will)"
        print(f"[{agora()}] dispositivo: {marca}")
        painel()
        return

    try:
        evento = json.loads(bruto)
    except json.JSONDecodeError:
        descartados += 1
        print(f"[{agora()}] REJEITADO payload nao e JSON valido")
        return

    motivo = validar(evento)
    if motivo:
        descartados += 1
        print(f"[{agora()}] REJEITADO {motivo}")
        return

    # Ordem e perda: o sequence torna visivel o que o transporte nao conta.
    seq = evento["sequence"]
    if ultima_sequencia is not None:
        if seq < ultima_sequencia:
            print(f"[{agora()}] AVISO evento fora de ordem "
                  f"(sequence {seq} apos {ultima_sequencia})")
        elif seq > ultima_sequencia + 1:
            perdidos = seq - ultima_sequencia - 1
            print(f"[{agora()}] AVISO salto na sequencia: "
                  f"{perdidos} evento(s) nao recebido(s)")
    ultima_sequencia = max(seq, ultima_sequencia or 0)

    ids_processados.add(evento["eventId"])
    recebidos += 1

    anterior, estado_atual = estado_atual, evento["state"]
    valor = evento.get("value")
    valor_txt = "--" if valor is None else f"{valor:.1f} bpm"

    print(f"[{agora()}] EVENTO  seq={seq}  {evento['eventType']}")
    print(f"           entidade : {evento['entityId']} (por {evento['deviceId']})")
    print(f"           estado   : {anterior} -> {estado_atual}")
    print(f"           valor    : {valor_txt}   movimento: {evento.get('motion','?')}")
    print(f"           cobertura: FC {evento.get('coverageFc','?')} "
          f"| MOV {evento.get('coverageMov','?')}")
    print(f"           razao    : {evento.get('reason','?')}")

    if estado_atual == "ATENCAO":
        print(f"\n  {CORES['ATENCAO']}>>> ALERTA AO CUIDADOR: "
              f"FC elevada em repouso, condicao persistente{RESET}")
    painel()


def main() -> int:
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:          # paho-mqtt 1.x
        client = mqtt.Client()

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    print("=== MARCO 2 | CONSUMIDOR | MQTT -> efeito observavel ===")
    try:
        client.connect(BROKER, PORTA, keepalive=30)
    except OSError as erro:
        print(f"nao foi possivel conectar a {BROKER}:{PORTA} -> {erro}")
        return 1

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nencerrando consumidor")
        client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
