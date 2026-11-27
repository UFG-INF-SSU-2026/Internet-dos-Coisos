package br.ufg.coisos

import android.app.Application
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

private const val INTERVALO_MS = 2_000L   // estado e movimento a cada 2 s

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
        aviso = null
        carregando = true
        erroLogin = motivo
    }

    fun reconhecerAlerta() {
        val cliente = api ?: return
        viewModelScope.launch {
            aviso = try {
                cliente.reconhecerAlerta()
                null                       // o status do comando aparece na tela
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
                        cliente.enviarMovimento(intensidade, capturado)
                        "%.2f g enviado".format(intensidade)
                    } catch (e: ErroApi) {
                        if (e.codigo == 401) { sair("Sessão expirou, entre de novo"); return@launch }
                        "leitura descartada: ${e.message}"
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

// --- Visual ---

private val Fundo = Color(0xFFF4F6F8)
private val Tinta = Color(0xFF1B2430)
private val Apagado = Color(0xFF6B7684)
private val Marca = Color(0xFF0F766E)

private val tema = lightColorScheme(
    primary = Marca,
    onPrimary = Color.White,
    background = Fundo,
    surface = Fundo,
    onBackground = Tinta,
    onSurface = Tinta,
    error = Color(0xFFC62828),
)

/** Cor forte e cor de fundo de cada tom do estado. */
private fun cores(tom: Tom): Pair<Color, Color> = when (tom) {
    Tom.BOM -> Color(0xFF2E7D32) to Color(0xFFE6F4EA)
    Tom.ALERTA -> Color(0xFFC62828) to Color(0xFFFDECEC)
    Tom.NEUTRO -> Color(0xFF546E7A) to Color(0xFFE9EDF0)
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = tema) {
                Surface(Modifier.fillMaxSize(), color = Fundo) {
                    val vm: CuidadorViewModel = viewModel()
                    Box(Modifier.safeDrawingPadding()) {
                        if (vm.api == null) TelaLogin(vm) else TelaEstado(vm)
                    }
                }
            }
        }
    }
}

@Composable
private fun Marca(tamanho: Int) {
    Box(
        Modifier.size(tamanho.dp).background(Marca, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        // Coração desenhado: o caractere ♥ muda de forma (e de cor, como emoji) entre fontes.
        Canvas(Modifier.size((tamanho * 0.5).dp)) {
            val w = size.width; val h = size.height
            drawPath(Path().apply {
                moveTo(w * 0.5f, h * 0.9f)
                cubicTo(w * 0.1f, h * 0.6f, -w * 0.05f, h * 0.25f, w * 0.25f, h * 0.12f)
                cubicTo(w * 0.4f, h * 0.06f, w * 0.5f, h * 0.18f, w * 0.5f, h * 0.26f)
                cubicTo(w * 0.5f, h * 0.18f, w * 0.6f, h * 0.06f, w * 0.75f, h * 0.12f)
                cubicTo(w * 1.05f, h * 0.25f, w * 0.9f, h * 0.6f, w * 0.5f, h * 0.9f)
                close()
            }, Color.White)
        }
    }
}

@Composable
fun TelaLogin(vm: CuidadorViewModel) {
    var url by rememberSaveable { mutableStateOf("https://") }
    var usuario by rememberSaveable { mutableStateOf("cuidador01") }
    var senha by rememberSaveable { mutableStateOf("") }
    val forma = RoundedCornerShape(14.dp)
    Column(
        Modifier.fillMaxSize().padding(horizontal = 28.dp).verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Spacer(Modifier.height(56.dp))
        Marca(72)
        Text("Coisos Cuidador", fontSize = 26.sp, fontWeight = FontWeight.Bold)
        Text("Acompanhe o paciente e responda aos alertas", color = Apagado, textAlign = TextAlign.Center)
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(url, { url = it }, label = { Text("Servidor (https://)") }, singleLine = true,
            shape = forma, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            modifier = Modifier.fillMaxWidth())
        OutlinedTextField(usuario, { usuario = it }, label = { Text("Usuário") }, singleLine = true,
            shape = forma, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(senha, { senha = it }, label = { Text("Senha") }, singleLine = true,
            shape = forma, visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { vm.entrar(url, usuario, senha) }),
            modifier = Modifier.fillMaxWidth())
        vm.erroLogin?.let { Text(it, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center) }
        Button(onClick = { vm.entrar(url, usuario, senha) }, enabled = !vm.entrando, shape = forma,
            modifier = Modifier.fillMaxWidth().height(52.dp)) {
            if (vm.entrando) CircularProgressIndicator(Modifier.size(22.dp), color = Color.White, strokeWidth = 2.dp)
            else Text("Entrar", fontSize = 16.sp)
        }
        Spacer(Modifier.height(32.dp))
    }
}

@Composable
fun TelaEstado(vm: CuidadorViewModel) {
    val r = vm.resumo
    Column(
        Modifier.fillMaxSize().padding(horizontal = 20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(Modifier.padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Marca(40)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("Paciente", color = Apagado, fontSize = 13.sp)
                Text(vm.api?.paciente ?: "—", fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
            }
            TextButton(onClick = { vm.sair() }) { Text("Sair") }
        }

        // Sem rede com dado antigo: avisa sem esconder o último estado.
        if (vm.erroRede != null) {
            Faixa(if (r == null) "Sem conexão com a API" else "Sem conexão. Mostrando o último estado recebido.")
        }

        when {
            vm.carregando -> Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            r != null -> {
                CartaoEstado(r)
                Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    val fonte = when (r.fonteMovimento) { "celular" -> "medido pelo celular"; "esp32" -> "medido pelo ESP32"; else -> null }
                    Info("Movimento", textoMovimento(r.movimento, r.fonteMovimento), fonte,
                        Modifier.weight(1f).fillMaxHeight())
                    Info("Dispositivo", if (r.online) "Conectado" else "Sem contato",
                        "última leitura ${horaLocal(r.ultimoContato)}", Modifier.weight(1f).fillMaxHeight())
                }
                if (r.podeReconhecer) {
                    Button(onClick = vm::reconhecerAlerta, shape = RoundedCornerShape(16.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = cores(Tom.ALERTA).first),
                        modifier = Modifier.fillMaxWidth().height(56.dp)) {
                        Text("Reconhecer alerta", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
                textoComando(r.statusComando)?.let { Info("Reconhecimento", it, null, Modifier.fillMaxWidth()) }
            }
        }
        vm.aviso?.let { Faixa(it) }

        Spacer(Modifier.weight(1f))
        Text("Balance o celular para simular o paciente em movimento. Sensor: ${vm.envioMovimento}",
            color = Apagado, fontSize = 12.sp, textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp))
    }
}

@Composable
fun CartaoEstado(r: Resumo) {
    val a = aparenciaDoEstado(r.estado)
    val (forte, fundo) = cores(a.tom)
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = fundo),
        modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(24.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(12.dp).background(forte, CircleShape))
                Spacer(Modifier.width(10.dp))
                Text(a.titulo, color = forte, fontSize = 24.sp, fontWeight = FontWeight.Bold)
            }
            Text(a.descricao, color = Tinta, modifier = Modifier.padding(top = 6.dp))
            Row(Modifier.padding(top = 20.dp), verticalAlignment = Alignment.Bottom) {
                Text(r.fcBpm, fontSize = 56.sp, fontWeight = FontWeight.Bold, color = Tinta, lineHeight = 56.sp)
                Text(" bpm", fontSize = 20.sp, color = Apagado, modifier = Modifier.padding(bottom = 8.dp))
            }
            Text("frequência cardíaca média", color = Apagado, fontSize = 13.sp)
        }
    }
}

@Composable
private fun Info(rotulo: String, valor: String, detalhe: String?, modifier: Modifier) {
    Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White),
        modifier = modifier) {
        Column(Modifier.padding(16.dp)) {
            Text(rotulo, color = Apagado, fontSize = 13.sp)
            Text(valor, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 4.dp))
            detalhe?.let { Text(it, color = Apagado, fontSize = 12.sp, modifier = Modifier.padding(top = 2.dp)) }
        }
    }
}

@Composable
private fun Faixa(texto: String) {
    Surface(shape = RoundedCornerShape(14.dp), color = Color(0xFFFFF4E5), modifier = Modifier.fillMaxWidth()) {
        Text(texto, color = Color(0xFF8A5300), modifier = Modifier.padding(14.dp))
    }
}
