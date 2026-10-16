"""Marco 3: regra de análise das leituras (portada do sketch.ino do Marco 2).

Só a análise: nada de HTTP, login ou chave aqui. Recebe leituras e o instante
(em segundos, relógio do servidor) e decide o estado do paciente.
"""

from collections import deque

# Valores do modo demonstração do Marco 2 (janelas curtas para caber na aula).
JANELA_FC_S = 20            # média da FC nos últimos 20 s
JANELA_MOV_S = 10           # movimento predominante nos últimos 10 s
TEMPO_MINIMO_ESTADO_S = 10  # evita ATENCAO/NORMAL alternando a cada lote
COBERTURA_MINIMA = 0.70     # abaixo de 70% de leituras válidas: DADOS_INSUFICIENTES
FC_LIMIAR_ENTRADA = 100.0   # entra em ATENCAO acima disso...
FC_LIMIAR_SAIDA = 92.0      # ...e só sai abaixo disso (histerese)
AVALIACOES_PARA_ENTRAR = 2  # a condição precisa persistir em 2 avaliações seguidas
FC_MIN, FC_MAX = 30.0, 220.0
G_REST_TOLERANCIA = 0.15    # |aceleração - 1 g| até 0,15 g = repouso
G_MAX = 8.0


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
        self.amostras = deque()      # (instante_s, fc ou None, movimento)
        self.estado = None           # None = ainda nenhuma avaliação
        self.entrou_em = None
        self.persistencia = 0
        self.transicoes = 0
        self.resumo = {}
        self.historico = deque(maxlen=20)

    def adicionar(self, leituras, agora):
        """Uma leitura por segundo; a última do lote foi medida em 'agora'."""
        n = len(leituras)
        for i, leitura in enumerate(leituras):
            self.amostras.append((agora - (n - 1 - i), fc_valida(leitura.get('fc')),
                                  movimento(leitura.get('g'))))
        return self.avaliar(agora)

    def calcular(self, agora):
        """Média, movimento predominante e cobertura das janelas."""
        while self.amostras and self.amostras[0][0] <= agora - JANELA_FC_S:
            self.amostras.popleft()
        fcs = [fc for t, fc, _ in self.amostras if fc is not None]
        movs = [m for t, _, m in self.amostras if t > agora - JANELA_MOV_S and m != 'INVALIDO']
        repouso = movs.count('REST') >= movs.count('ACTIVE')
        return {
            'fcMedia': round(sum(fcs) / len(fcs), 1) if fcs else None,
            'movimento': 'INVALIDO' if not movs else ('REST' if repouso else 'ACTIVE'),
            'coberturaFc': round(min(1.0, len(fcs) / JANELA_FC_S), 2),
            'coberturaMov': round(min(1.0, len(movs) / JANELA_MOV_S), 2),
        }

    def avaliar(self, agora):
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
                return self._transitar('NORMAL', 'condicao_cessou', agora)
            return None

        condicao = r['fcMedia'] > FC_LIMIAR_ENTRADA and repouso
        self.persistencia = self.persistencia + 1 if condicao else 0
        if self.persistencia >= AVALIACOES_PARA_ENTRAR and self._tempo_minimo(agora):
            return self._transitar('ATENCAO', 'condicao_persistiu', agora)
        return self._transitar('NORMAL', 'janela_com_cobertura', agora)

    def verificar_silencio(self, agora):
        """Sem lotes chegando a cobertura cai; chamado quando o painel consulta."""
        if self.estado is None:
            return None
        r = self.calcular(agora)
        if r['coberturaFc'] < COBERTURA_MINIMA or r['coberturaMov'] < COBERTURA_MINIMA:
            self.resumo, self.persistencia = r, 0
            return self._transitar('DADOS_INSUFICIENTES', 'sem_leituras_recentes', agora)
        return None

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
