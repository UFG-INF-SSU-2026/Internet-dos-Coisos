-- Marco 3 consolidado: esquema equivalente a armazenamento.py.
-- Execute no SQL Editor do Tiger Cloud, SOMENTE se desejar preparar manualmente.
-- A API cria essas estruturas automaticamente na primeira conexao bem-sucedida.
-- Exige PostgreSQL com extensao TimescaleDB INSTALADA no servidor.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS leituras (
  ts TIMESTAMPTZ NOT NULL,
  patient_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  lote_id TEXT NOT NULL,
  fc DOUBLE PRECISION,
  g DOUBLE PRECISION
);
SELECT create_hypertable('leituras', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_leituras_paciente_tempo ON leituras(patient_id, ts DESC);

CREATE TABLE IF NOT EXISTS eventos_estado (
  ts TIMESTAMPTZ NOT NULL,
  patient_id TEXT NOT NULL,
  estado TEXT NOT NULL,
  razao TEXT,
  fc_media DOUBLE PRECISION,
  movimento TEXT,
  cobertura_fc DOUBLE PRECISION,
  cobertura_mov DOUBLE PRECISION
);
SELECT create_hypertable('eventos_estado', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_eventos_paciente_tempo ON eventos_estado(patient_id, ts DESC);

CREATE TABLE IF NOT EXISTS comandos (
  ts TIMESTAMPTZ NOT NULL,
  patient_id TEXT NOT NULL,
  command_id TEXT NOT NULL,
  tipo TEXT NOT NULL,
  status TEXT NOT NULL,
  emitido_por TEXT
);
SELECT create_hypertable('comandos', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_comandos_paciente_tempo ON comandos(patient_id, ts DESC);
