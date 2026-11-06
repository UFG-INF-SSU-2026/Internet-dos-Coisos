"""Interface utilizada pela API para o armazenamento do colega (armazenamento.py).

Concentramos as escritas em UMA implementacao: ``Armazenamento`` da branch
``timescaledb``. Esta interface existe apenas para manter a API mais simples e
permitir rodar sem driver/banco quando se esta desenvolvendo o simulador.
"""

import os
from datetime import datetime, timezone


class HistoricoTemporal:
    def __init__(self, url=None):
        self.url = url if url is not None else os.getenv('DATABASE_URL', '')
        self.backend = None
        self._erro = None
        if self.url:
            try:
                from armazenamento import Armazenamento
                self.backend = Armazenamento(self.url)
            except ImportError:
                self._erro = 'Instale psycopg[binary] para usar TimescaleDB'

    @property
    def configurado(self):
        return bool(self.url)

    @property
    def ativo(self):
        return bool(self.backend and self.backend.ativo)

    @property
    def erro(self):
        return self.backend.erro if self.backend else self._erro

    @property
    def descartadas(self):
        return self.backend.gravacoes_descartadas if self.backend else 0

    def gravar_lote(self, device_id, patient_id, lote_id, leituras, estado=None):
        # Mantem a assinatura anteriormente usada pela fila; o estado eh gravado
        # separadamente em eventos_estado quando ha mudanca de estado.
        if self.backend:
            return self.backend.gravar_lote(patient_id, device_id, lote_id, leituras,
                                           datetime.now(timezone.utc))
        return False

    def gravar_transicao(self, patient_id, evento):
        if self.backend:
            return self.backend.gravar_transicao(patient_id, evento)
        return False

    def gravar_comando(self, patient_id, comando):
        if self.backend:
            return self.backend.gravar_comando(patient_id, comando)
        return False

    def consultar(self, patient_id, limite=100):
        if self.backend:
            retorno = self.backend.consultar(patient_id, limite)
            return retorno if retorno is not None else []
        return []
