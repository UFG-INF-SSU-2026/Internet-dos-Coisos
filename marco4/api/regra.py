"""Marco 4: regra de análise das leituras (portada do sketch.ino do Marco 2).

Só a análise: nada de HTTP, login ou chave aqui. Recebe leituras e o instante
(em segundos, relógio do servidor) e decide o estado do paciente.
"""

from collections import deque

# Tempos curtos para a demonstração de 5 min (o projeto original usava janela de 60 s).
# O ESP32 mede 1 leitura por segundo: 10 leituras = 10 s.
JANELA_FC = 10              # média da FC nas últimas 10 leituras
JANELA_MOV = 5              # movimento predominante nas últimas 5 leituras
COBERTURA_MINIMA = 0.70     # menos de 70% de leituras válidas: DADOS_INSUFICIENTES
SILENCIO_S = 8              # nenhum lote por 8 s: DADOS_INSUFICIENTES
TEMPO_MINIMO_ESTADO_S = 4   # evita ATENCAO/NORMAL alternando a cada lote
FC_LIMIAR_ENTRADA = 100.0   # entra em ATENCAO acima disso...
FC_LIMIAR_SAIDA = 92.0      # ...e só sai abaixo disso (histerese)
AVALIACOES_PARA_ENTRAR = 2  # a condição precisa persistir em 2 avaliações seguidas
FC_MIN, FC_MAX = 30.0, 220.0
G_REST_TOLERANCIA = 0.15    # |aceleração - 1 g| até 0,15 g = repouso
G_MAX = 8.0
# Marco 4: o celular do paciente é o segundo produtor (acelerômetro).
# Se ele relatou movimento nos últimos MOV_APP_VALIDO_S segundos, esse contexto
# prevalece sobre o MPU6050: paciente em movimento, alerta de FC alta suprimido.
MOV_APP_VALIDO_S = 6


def fc_valida(fc):
    """FC plausível ou None (sensor ausente ou fora de faixa)."""
    if isinstance(fc, bool) or not isinstance(fc, (int, float)):
        return None
    return float(fc) if FC_MIN <= fc <= FC_MAX else None


def movimento(g):
    """Classifica a magnitude da aceleração (em g): REST, ACTIVE ou INVALIDO."""
    if isinstance(g, bool) or not isinstance(g, (int, float)) or not 0 <= g <= G_MAX:
        return 'INVALIDO'
    return 'REST' if abs(g - 1.0) <= G_REST_TOLERANCIA else 'ACTIVE'


class Monitor:
    """Estado de um paciente calculado a partir das leituras que chegam."""

    def __init__(self):
        self.amostras = deque(maxlen=JANELA_FC)   # (fc ou None, movimento); as mais antigas saem sozinhas
        self.ultimo_lote_em = None
        self.estado = None           # None = ainda nenhuma avaliação
        self.entrou_em = None
        self.persistencia = 0
        self.transicoes = 0
        self.resumo = {}
        self.historico = deque(maxlen=20)
        self.mov_app = None          # (movimento, instante) da última leitura do celular

    def restaurar(self, leituras, historico, agora, idade_ultimo_lote_s=0.0):
        """Reconstrói a janela e o último estado a partir do snapshot do banco.

        O contexto do celular não é restaurado: D31 não persiste amostras móveis,
        portanto ele precisa ser observado novamente após o reinício.
        """
        self.amostras.clear()
        for leitura in leituras[-JANELA_FC:]:
            self.amostras.append((fc_valida(leitura.get('fc')), movimento(leitura.get('g'))))

        idade = max(0.0, float(idade_ultimo_lote_s))
        self.ultimo_lote_em = agora - idade if leituras else None
        self.mov_app = None
        self.persistencia = 0
        self.historico.clear()

        for indice, evento in enumerate(historico[-20:], start=1):
            self.historico.append({
                'sequence': indice,
                'estado': evento.get('estado', 'SEM_DADOS'),
                'razao': evento.get('razao', 'restaurado'),
                'horaUtc': evento.get('horaUtc'),
                'fcMedia': evento.get('fcMedia'),
                'movimento': evento.get('movimento'),
                'coberturaFc': evento.get('coberturaFc'),
                'coberturaMov': evento.get('coberturaMov'),
            })

        if self.historico:
            self.estado = self.historico[-1]['estado']
            self.entrou_em = agora
            self.transicoes = len(self.historico)
            self.resumo = self.calcular(agora)
        else:
            self.estado = None
            self.entrou_em = None
            self.transicoes = 0
            self.resumo = {}
            if self.amostras:
                self.avaliar(agora, conta_persistencia=False)

    def adicionar(self, leituras, agora):
        """Guarda as leituras do lote e reavalia o estado."""
        for leitura in leituras:
            self.amostras.append((fc_valida(leitura.get('fc')), movimento(leitura.get('g'))))
        self.ultimo_lote_em = agora
        return self.avaliar(agora)

    def registrar_movimento_app(self, intensidade, agora):
        """Leitura do celular: intensidade = |aceleração - 1 g|, em g.

        Só reavalia com leituras recentes do ESP32: sem FC não há o que suprimir, e
        janela velha não pode tirar o paciente de DADOS_INSUFICIENTES.
        A leitura do celular pode suprimir ou encerrar um alerta, mas não conta
        para a persistência de entrada: o alerta continua exigindo 2 lotes do ESP32.
        """
        mov = 'REST' if intensidade <= G_REST_TOLERANCIA else 'ACTIVE'
        self.mov_app = (mov, agora)
        if self.ultimo_lote_em is None or agora - self.ultimo_lote_em > SILENCIO_S:
            return None
        return self.avaliar(agora, conta_persistencia=False)

    def calcular(self, agora=None):
        """Média, movimento predominante e cobertura das janelas."""
        fcs = [fc for fc, _ in self.amostras if fc is not None]
        movs = [m for _, m in list(self.amostras)[-JANELA_MOV:] if m != 'INVALIDO']
        repouso = movs.count('REST') >= movs.count('ACTIVE')
        movimento_borda = 'INVALIDO' if not movs else ('REST' if repouso else 'ACTIVE')
        movimento_final, fonte = movimento_borda, 'esp32'
        if (self.mov_app and agora is not None
                and agora - self.mov_app[1] <= MOV_APP_VALIDO_S
                and self.mov_app[0] == 'ACTIVE'):
            movimento_final, fonte = 'ACTIVE', 'celular'   # mudança de contexto
        return {
            'fcMedia': round(sum(fcs) / len(fcs), 1) if fcs else None,
            'movimento': movimento_final,
            'fonteMovimento': fonte,
            'movimentoEsp32': movimento_borda,
            'movimentoCelular': (self.mov_app[0] if self.mov_app and agora is not None
                                 and agora - self.mov_app[1] <= MOV_APP_VALIDO_S else None),
            'coberturaFc': round(len(fcs) / JANELA_FC, 2),
            'coberturaMov': round(len(movs) / JANELA_MOV, 2),
        }

    def avaliar(self, agora, conta_persistencia=True):
        """Aplica a regra; devolve o evento de transição ou None se o estado não mudou."""
        r = self.resumo = self.calcular(agora)
        if r['coberturaFc'] < COBERTURA_MINIMA or r['coberturaMov'] < COBERTURA_MINIMA:
            self.persistencia = 0
            return self._transitar('DADOS_INSUFICIENTES', 'cobertura_insuficiente', agora)

        repouso = r['movimento'] == 'REST'
        if self.estado == 'ATENCAO':
            mantida = r['fcMedia'] > FC_LIMIAR_SAIDA and repouso
            if not mantida and self._tempo_minimo(agora):
                self.persistencia = 0
                razao = ('movimento_no_celular' if r['fonteMovimento'] == 'celular'
                         else 'condicao_cessou')
                return self._transitar('NORMAL', razao, agora)
            return None

        condicao = r['fcMedia'] > FC_LIMIAR_ENTRADA and repouso
        if not condicao:
            self.persistencia = 0
        elif conta_persistencia:
            self.persistencia += 1
        if self.persistencia >= AVALIACOES_PARA_ENTRAR and self._tempo_minimo(agora):
            return self._transitar('ATENCAO', 'condicao_persistiu', agora)
        return self._transitar('NORMAL', 'janela_com_cobertura', agora)

    def verificar_silencio(self, agora):
        """Nenhum lote há SILENCIO_S segundos (rede caiu): chamado quando o painel consulta."""
        if self.ultimo_lote_em is None or agora - self.ultimo_lote_em <= SILENCIO_S:
            return None
        self.persistencia = 0
        return self._transitar('DADOS_INSUFICIENTES', 'sem_leituras_recentes', agora)

    def _tempo_minimo(self, agora):
        return self.entrou_em is None or agora - self.entrou_em >= TEMPO_MINIMO_ESTADO_S

    def _transitar(self, novo, razao, agora):
        if novo == self.estado:
            return None
        self.estado, self.entrou_em = novo, agora
        self.transicoes += 1
        evento = {'sequence': self.transicoes, 'estado': novo, 'razao': razao, **self.resumo}
        self.historico.append(evento)
        return evento
