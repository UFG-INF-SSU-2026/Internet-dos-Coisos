package br.ufg.coisos

import android.app.Application
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

private const val INTERVALO_MS = 2_000L

class CuidadorViewModel(app: Application) : AndroidViewModel(app) {
    var api: Api? by mutableStateOf(null); private set
    var entrando by mutableStateOf(false); private set
    var erroLogin: String? by mutableStateOf(null); private set
    var carregando by mutableStateOf(true); private set
    var erroRede: String? by mutableStateOf(null); private set
    var resumo: Resumo? by mutableStateOf(null); private set
    var aviso: String? by mutableStateOf(null); private set
    var envioMovimento by mutableStateOf("aguardando sensor"); private set
    var consultandoHistorico by mutableStateOf(false); private set
    var historicoBanco by mutableStateOf<List<LeituraGrafico>>(emptyList()); private set
    var origemHistorico by mutableStateOf<String?>(null); private set
    var erroHistorico by mutableStateOf<String?>(null); private set

    private val movimento = Movimento(app)
    private var tarefas = listOf<Job>()

    fun entrar(url: String, usuario: String, senha: String) {
        erroLogin = null
        val cliente = try { Api(url) } catch (e: IllegalArgumentException) {
            erroLogin = e.message; return
        }
        entrando = true
        viewModelScope.launch {
            try {
                cliente.login(usuario, senha)
                api = cliente
                iniciarLacos(cliente)
            } catch (e: ErroApi) {
                erroLogin = if (e.codigo == 401) "Usuário ou senha incorretos" else e.message
            } catch (e: Exception) {
                erroLogin = "Sem conexão com a API: ${e.message}"
            } finally {
                entrando = false
            }
        }
    }

    fun sair(motivo: String? = null) {
        tarefas.forEach { it.cancel() }
        tarefas = emptyList()
        movimento.parar()
        api = null
        resumo = null
        historicoBanco = emptyList()
        origemHistorico = null
        erroHistorico = null
        carregando = true
        erroRede = null
        aviso = null
        erroLogin = motivo
    }

    fun reconhecerAlerta() {
        val cliente = api ?: return
        viewModelScope.launch {
            aviso = try {
                val comando = cliente.reconhecerAlerta()
                "Reconhecimento enviado (${comando.texto("commandId")}). Aguardando ESP32."
            } catch (e: ErroApi) {
                if (e.codigo == 401) {
                    sair("Sessão expirou, entre de novo")
                    return@launch
                }
                if (e.codigo == 409) "Não há alerta ativo para reconhecer" else e.message
            } catch (e: Exception) {
                "Falha de rede: ${e.message}"
            }
        }
    }

    fun consultarHistorico() {
        val cliente = api ?: return
        consultandoHistorico = true
        erroHistorico = null
        viewModelScope.launch {
            try {
                val resposta = cliente.historico(80)
                historicoBanco = leiturasDoHistorico(resposta)
                origemHistorico = resposta.texto("origem", "origem desconhecida")
                erroHistorico = if (resposta.isNull("erro")) null else resposta.texto("erro")
            } catch (e: ErroApi) {
                if (e.codigo == 401) {
                    sair("Sessão expirou, entre de novo")
                    return@launch
                }
                erroHistorico = e.message
            } catch (e: Exception) {
                erroHistorico = "Falha ao consultar histórico: ${e.message}"
            } finally {
                consultandoHistorico = false
            }
        }
    }

    private fun iniciarLacos(cliente: Api) {
        movimento.iniciar()
        if (!movimento.disponivel) envioMovimento = "celular sem acelerômetro"
        tarefas = listOf(
            // D25: polling REST no app; a Web usa WebSocket.
            viewModelScope.launch {
                while (isActive) {
                    try {
                        resumo = Resumo.de(cliente.estado())
                        erroRede = null
                    } catch (e: ErroApi) {
                        if (e.codigo == 401) {
                            sair("Sessão expirou, entre de novo")
                            return@launch
                        }
                        erroRede = e.message
                    } catch (e: Exception) {
                        erroRede = "Sem conexão: ${e.message}"
                    } finally {
                        carregando = false
                    }
                    delay(INTERVALO_MS)
                }
            },
            // O Android continua como segundo produtor, preservando sensor e contrato.
            viewModelScope.launch {
                while (isActive) {
                    delay(INTERVALO_MS)
                    val intensidade = movimento.coletar() ?: continue
                    envioMovimento = try {
                        val resposta = cliente.enviarMovimento(intensidade, System.currentTimeMillis())
                        "%.2f g enviado (%s)".format(
                            java.util.Locale.ROOT, intensidade, resposta.texto("movimento"),
                        )
                    } catch (e: ErroApi) {
                        if (e.codigo == 401) {
                            sair("Sessão expirou, entre de novo")
                            return@launch
                        }
                        "descartada pela API: ${e.message}"
                    } catch (e: Exception) {
                        "falha ao enviar: ${e.message}"
                    }
                }
            },
        )
    }

    override fun onCleared() {
        movimento.parar()
        tarefas.forEach { it.cancel() }
    }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(Modifier.fillMaxSize()) {
                    val vm: CuidadorViewModel = viewModel()
                    if (vm.api == null) TelaLogin(vm) else TelaEstado(vm)
                }
            }
        }
    }
}

@Composable
fun TelaLogin(vm: CuidadorViewModel) {
    var url by rememberSaveable { mutableStateOf("https://") }
    var usuario by rememberSaveable { mutableStateOf("cuidador01") }
    var senha by rememberSaveable { mutableStateOf("") }
    Column(Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Internet dos Coisos", style = MaterialTheme.typography.headlineSmall)
        Text("Entre com a conta do cuidador usada no painel web.")
        OutlinedTextField(url, { url = it }, label = { Text("URL HTTPS da API") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri), modifier = Modifier.fillMaxWidth())
        OutlinedTextField(usuario, { usuario = it }, label = { Text("Usuário") }, singleLine = true,
            modifier = Modifier.fillMaxWidth())
        OutlinedTextField(senha, { senha = it }, label = { Text("Senha") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth())
        vm.erroLogin?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(onClick = { vm.entrar(url, usuario, senha) }, enabled = !vm.entrando,
            modifier = Modifier.fillMaxWidth()) {
            if (vm.entrando) CircularProgressIndicator(Modifier.height(20.dp)) else Text("Entrar")
        }
    }
}

@Composable
fun TelaEstado(vm: CuidadorViewModel) {
    val r = vm.resumo
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 12.dp)
        .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Monitoramento", style = MaterialTheme.typography.headlineSmall)
                Text("Internet dos Coisos · ${vm.api?.paciente}", style = MaterialTheme.typography.bodySmall)
            }
            OutlinedButton(onClick = { vm.sair() }) { Text("Sair") }
        }
        if (vm.carregando && r == null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator()
                Spacer(Modifier.padding(8.dp))
                Text("Conectando à API…")
            }
        } else if (r == null) {
            Text(vm.erroRede ?: "Sem dados disponíveis", color = MaterialTheme.colorScheme.error)
        } else {
            CartaoEstado(r)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Metrica("FC média", r.fcMedia, Modifier.weight(1f))
                Metrica("Movimento", r.movimento, Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Metrica("Cobertura FC", r.coberturaFc, Modifier.weight(1f))
                Metrica("Cobertura MOV", r.coberturaMov, Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Metrica("Lotes recebidos", r.lotesRecebidos.toString(), Modifier.weight(1f))
                Metrica("Fila pendente", "${r.filaPendentes}/${r.capacidadeFila}", Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Metrica("Enfileirados", r.filaEnfileirados.toString(), Modifier.weight(1f))
                Metrica("Processados", r.filaProcessados.toString(), Modifier.weight(1f))
            }

            Secao("Evolução da frequência cardíaca") {
                GraficoFC(r.leiturasRecentes)
                Text("Linha tracejada: referência de 100 bpm. Dados sintéticos.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Secao("Ciclo 2 · Ação do cuidador") {
                Text(when (r.comandoStatus) {
                    "PENDENTE" -> "Aguardando o ESP32 receber o comando."
                    "ENTREGUE" -> "Entregue ao ESP32; aguardando confirmação (ACK)."
                    "EXECUTADO" -> "Execução confirmada pelo ESP32."
                    else -> "Nenhum comando ativo."
                })
                r.comandoId?.let { Text("Identificador: $it", style = MaterialTheme.typography.bodySmall) }
                r.comandoConfirmadoEm?.let {
                    Text("Confirmado às ${horaCurta(it)}", style = MaterialTheme.typography.bodySmall)
                }
                Button(onClick = vm::reconhecerAlerta, enabled = r.podeReconhecer,
                    modifier = Modifier.fillMaxWidth()) {
                    Text("Reconhecer alerta · silenciar buzzer")
                }
                vm.aviso?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            }
            Secao("Fila FIFO · últimos lotes") {
                if (r.ultimosLotes.isEmpty()) Text("Nenhum lote processado ainda.")
                else r.ultimosLotes.asReversed().forEach {
                    Text("${it.origem.uppercase()}: ${it.loteId}", style = MaterialTheme.typography.bodySmall)
                }
            }
            Secao("Mudanças de estado") {
                if (r.historico.isEmpty()) Text("Nenhuma transição registrada.")
                else r.historico.take(8).forEach {
                    Text("${horaCurta(it.horaUtc)} · ${it.estado} (${it.razao})",
                        style = MaterialTheme.typography.bodySmall)
                }
                Text("Último contato do ESP32: ${horaCurta(r.ultimoContato)}",
                    style = MaterialTheme.typography.bodySmall)
            }
            Secao("Persistência e segundo produtor") {
                Text("Banco temporal: ${r.persistencia}")
                r.erroPersistencia?.let { Text("Erro de persistência: $it", color = MaterialTheme.colorScheme.error) }
                if (r.gravacoesNaoPersistidas > 0) Text("Gravações não persistidas: ${r.gravacoesNaoPersistidas}")
                Text("Movimento do celular: ${r.movimentoCelular}")
                Text("Leituras do celular: ${r.celularRecebidas} recebidas · ${r.celularDescartadas} descartadas")
                Text("Última leitura: ${horaCurta(r.celularUltimaLeitura)}",
                    style = MaterialTheme.typography.bodySmall)
                Text("Acelerômetro: ${vm.envioMovimento}", style = MaterialTheme.typography.bodySmall)
            }
            Secao("Histórico no banco temporal") {
                Button(onClick = vm::consultarHistorico, enabled = !vm.consultandoHistorico,
                    modifier = Modifier.fillMaxWidth()) {
                    if (vm.consultandoHistorico) CircularProgressIndicator(Modifier.height(18.dp))
                    else Text("Consultar histórico (até 80 leituras)")
                }
                vm.origemHistorico?.let { Text("Origem: $it", style = MaterialTheme.typography.bodySmall) }
                vm.erroHistorico?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                if (vm.historicoBanco.isNotEmpty()) {
                    vm.historicoBanco.asReversed().take(8).forEach {
                        val fc = it.fc?.let { valor -> "%.1f".format(java.util.Locale.ROOT, valor) } ?: "—"
                        Text("${horaCurta(it.recebidoEmUtc)} · FC $fc bpm · ${it.loteId}",
                            style = MaterialTheme.typography.bodySmall)
                    }
                } else if (vm.origemHistorico != null && vm.erroHistorico == null) {
                    Text("Nenhuma leitura encontrada.")
                }
            }
        }
        if (vm.erroRede != null) {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                Text("Erro de rede: ${vm.erroRede}. ${if (r != null) "Mostrando o último estado recebido." else ""}",
                    Modifier.padding(12.dp), color = MaterialTheme.colorScheme.onErrorContainer)
            }
        }
        Text("Protótipo acadêmico com dados sintéticos; não utilizar para decisões médicas.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun CartaoEstado(r: Resumo) {
    val cor = when (r.estado) {
        "ATENCAO" -> Color(0xFFFFCDD2)
        "NORMAL" -> Color(0xFFC8E6C9)
        else -> Color(0xFFDBEAFE)
    }
    val texto = when (r.estado) {
        "ATENCAO" -> Color(0xFF991B1B)
        "NORMAL" -> Color(0xFF166534)
        else -> Color(0xFF1E40AF)
    }
    Card(colors = CardDefaults.cardColors(containerColor = cor), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(r.estado.replace('_', ' '), color = texto,
                style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(if (r.online) "ESP32 · contato recente" else "ESP32 · sem contato recente", color = texto)
            Text("Movimento: ${r.movimento} · fonte: ${r.fonteMovimento}", color = texto)
        }
    }
}

@Composable
private fun Metrica(titulo: String, valor: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(titulo, style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(valor, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun Secao(titulo: String, conteudo: @Composable () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(titulo, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            conteudo()
        }
    }
}

@Composable
private fun GraficoFC(leituras: List<LeituraGrafico>) {
    val pontos = leituras.mapNotNull { it.fc }
    if (pontos.isEmpty()) {
        Text("Aguardando leituras válidas de frequência cardíaca.")
        return
    }
    val linha = MaterialTheme.colorScheme.primary
    val referencia = MaterialTheme.colorScheme.error
    Canvas(Modifier.fillMaxWidth().height(170.dp).background(MaterialTheme.colorScheme.surface)) {
        val esquerda = 12f
        val direita = size.width - 12f
        val topo = 12f
        val base = size.height - 12f
        fun y(valor: Double): Float =
            base - ((valor.coerceIn(30.0, 220.0) - 30.0) / 190.0).toFloat() * (base - topo)
        drawLine(color = referencia, start = Offset(esquerda, y(100.0)),
            end = Offset(direita, y(100.0)), strokeWidth = 2f,
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 7f)))
        if (pontos.size == 1) {
            drawCircle(linha, 5f, Offset(size.width / 2f, y(pontos.first())))
        } else {
            val caminho = Path()
            pontos.forEachIndexed { index, valor ->
                val x = esquerda + index.toFloat() * (direita - esquerda) / (pontos.size - 1)
                val ponto = Offset(x, y(valor))
                if (index == 0) caminho.moveTo(ponto.x, ponto.y) else caminho.lineTo(ponto.x, ponto.y)
                drawCircle(linha, 3.5f, ponto)
            }
            drawPath(caminho, linha,
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 3f, cap = StrokeCap.Round))
        }
    }
}

private fun horaCurta(valor: String): String {
    if (valor.isBlank() || valor == "—") return "—"
    return valor.substringAfter('T', valor).take(8)
}
