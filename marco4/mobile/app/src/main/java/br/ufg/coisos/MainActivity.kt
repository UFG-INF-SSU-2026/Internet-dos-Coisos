package br.ufg.coisos

import android.app.Application
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
import org.json.JSONObject

private const val INTERVALO_MS = 2_000L   // estado e movimento a cada 2 s

/** optString devolve o texto "null" para JSON null; aqui vira o valor padrão. */
private fun JSONObject.texto(chave: String, padrao: String = "—"): String =
    if (isNull(chave)) padrao else optString(chave, padrao)

/** O que a tela de estado mostra, extraído da resposta de /estado. */
data class Resumo(
    val estado: String,
    val fcMedia: String,
    val movimento: String,
    val fonteMovimento: String,
    val online: Boolean,
    val ultimoContato: String,
    val comando: String?,
) {
    companion object {
        fun de(j: JSONObject): Resumo {
            val r = j.optJSONObject("resumo") ?: JSONObject()
            val c = j.optJSONObject("comando")
            return Resumo(
                estado = j.texto("estado", "SEM_DADOS"),
                fcMedia = if (r.isNull("fcMedia")) "—" else "${r.optDouble("fcMedia")} bpm",
                movimento = r.texto("movimento"),
                fonteMovimento = r.texto("fonteMovimento"),
                online = j.optBoolean("online"),
                ultimoContato = j.texto("ultimoContatoUtc"),
                comando = c?.let { "${it.optString("commandId")}: ${it.optString("status")}" },
            )
        }
    }
}

class CuidadorViewModel(app: Application) : AndroidViewModel(app) {
    var api: Api? by mutableStateOf(null); private set
    var entrando by mutableStateOf(false); private set
    var erroLogin: String? by mutableStateOf(null); private set

    var carregando by mutableStateOf(true); private set
    var erroRede: String? by mutableStateOf(null); private set
    var resumo: Resumo? by mutableStateOf(null); private set
    var aviso: String? by mutableStateOf(null); private set
    var envioMovimento by mutableStateOf("aguardando sensor"); private set

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
        movimento.parar()
        api = null
        resumo = null
        carregando = true
        erroLogin = motivo
    }

    fun reconhecerAlerta() {
        val cliente = api ?: return
        viewModelScope.launch {
            aviso = try {
                val c = cliente.reconhecerAlerta()
                "Reconhecimento enviado (${c.texto("commandId")}). Acompanhe o status no cartão."
            } catch (e: ErroApi) {
                if (e.codigo == 401) { sair("Sessão expirou, entre de novo"); return@launch }
                if (e.codigo == 409) "Não há alerta ativo para reconhecer" else e.message
            } catch (e: Exception) {
                "Falha de rede: ${e.message}"
            }
        }
    }

    private fun iniciarLacos(cliente: Api) {
        movimento.iniciar()
        if (!movimento.disponivel) envioMovimento = "celular sem acelerômetro"
        tarefas = listOf(
            // Tela de estado: consulta a cada 2 s (mais simples que WebSocket no app).
            viewModelScope.launch {
                while (isActive) {
                    try {
                        resumo = Resumo.de(cliente.estado())
                        erroRede = null
                    } catch (e: ErroApi) {
                        if (e.codigo == 401) { sair("Sessão expirou, entre de novo"); return@launch }
                        erroRede = e.message
                    } catch (e: Exception) {
                        erroRede = "Sem conexão: ${e.message}"
                    } finally {
                        carregando = false
                    }
                    delay(INTERVALO_MS)
                }
            },
            // Segundo produtor: intensidade do movimento com a hora de captura.
            viewModelScope.launch {
                while (isActive) {
                    delay(INTERVALO_MS)
                    val intensidade = movimento.coletar() ?: continue
                    val capturado = System.currentTimeMillis()
                    envioMovimento = try {
                        val r = cliente.enviarMovimento(intensidade, capturado)
                        "%.2f g enviado (%s)".format(intensidade, r.texto("movimento"))
                    } catch (e: ErroApi) {
                        if (e.codigo == 401) { sair("Sessão expirou, entre de novo"); return@launch }
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
    Column(
        Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Internet dos Coisos", style = MaterialTheme.typography.headlineSmall)
        Text("Entre com o usuário do cuidador. A URL é a https:// do túnel Cloudflare.")
        OutlinedTextField(url, { url = it }, label = { Text("URL da API") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            modifier = Modifier.fillMaxWidth())
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
    Column(
        Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Paciente ${vm.api?.paciente}", style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.weight(1f))
            OutlinedButton(onClick = { vm.sair() }) { Text("Sair") }
        }
        val r = vm.resumo
        when {
            vm.carregando -> Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(); Spacer(Modifier.padding(8.dp)); Text("Carregando…")
            }
            r == null -> Text(vm.erroRede ?: "Sem dados", color = MaterialTheme.colorScheme.error)
            else -> CartaoEstado(r)
        }
        // Erro de rede com dado antigo na tela: avisa sem esconder o último estado.
        if (r != null && vm.erroRede != null) {
            Text("Erro de rede: ${vm.erroRede}. Mostrando o último estado recebido.",
                color = MaterialTheme.colorScheme.error)
        }
        Button(onClick = vm::reconhecerAlerta, enabled = r?.estado == "ATENCAO",
            modifier = Modifier.fillMaxWidth()) { Text("Reconhecer alerta") }
        vm.aviso?.let { Text(it) }
        Text("Acelerômetro: ${vm.envioMovimento}", style = MaterialTheme.typography.bodySmall)
        Text("Balance o celular para simular o paciente em movimento: o alerta de FC alta fica suprimido.",
            style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
fun CartaoEstado(r: Resumo) {
    val cor = when (r.estado) {
        "ATENCAO" -> Color(0xFFFFCDD2)
        "NORMAL" -> Color(0xFFC8E6C9)
        else -> Color(0xFFE0E0E0)
    }
    Card(colors = CardDefaults.cardColors(containerColor = cor), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(r.estado, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text("FC média: ${r.fcMedia}")
            Text("Movimento: ${r.movimento} (fonte: ${r.fonteMovimento})")
            Text(if (r.online) "ESP32 online" else "ESP32 sem contato recente")
            Text("Último contato: ${r.ultimoContato}", style = MaterialTheme.typography.bodySmall)
            r.comando?.let { Text("Comando: $it") }
        }
    }
}
