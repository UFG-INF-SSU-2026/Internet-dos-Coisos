package br.ufg.coisos

import org.json.JSONObject
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sqrt

/*
 * Regras do app sem dependência do Android, para os testes de unidade em
 * app/src/test rodarem na JVM, sem emulador.
 */

/** Gravidade padrão em m/s², o mesmo valor de SensorManager.GRAVITY_EARTH. */
const val GRAVIDADE = 9.80665

/** Intensidade máxima aceita pela API (contrato app-v1). */
const val INTENSIDADE_MAX = 8.0

/** |‖a‖ / g − 1|: 0 com o celular parado em qualquer posição e cresce com o movimento. */
fun intensidadeMovimento(x: Float, y: Float, z: Float): Double {
    val modulo = sqrt((x * x + y * y + z * z).toDouble())
    return abs(modulo / GRAVIDADE - 1.0)
}

/** Normaliza a URL digitada; só aceita https:// para o token não trafegar em claro. */
fun urlDaApi(digitada: String): String {
    val base = digitada.trim().trimEnd('/')
    require(base.startsWith("https://") && base.length > "https://".length) { "Use a URL https:// do túnel" }
    return base
}

/** Corpo de POST /api/app/leituras, com a intensidade limitada à faixa do contrato. */
fun corpoMovimento(paciente: String, intensidade: Double, capturadoEmMs: Long): JSONObject =
    JSONObject()
        .put("entityId", paciente)
        .put("intensidade", intensidade.coerceIn(0.0, INTENSIDADE_MAX))
        .put("capturadoEmMs", capturadoEmMs)

/** optString devolve o texto "null" para JSON null; aqui vira o valor padrão. */
fun JSONObject.texto(chave: String, padrao: String = "—"): String =
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
    val fcBpm: String = "—",
    val statusComando: String? = null,
    /** O último comando foi emitido depois do início do estado atual (é deste alerta). */
    val comandoDesteAlerta: Boolean = false,
) {
    /** O botão "Reconhecer alerta" só faz sentido com alerta ativo ainda não reconhecido. */
    val podeReconhecer: Boolean get() = estado == "ATENCAO" && !comandoDesteAlerta

    companion object {
        fun de(j: JSONObject): Resumo {
            val r = j.optJSONObject("resumo") ?: JSONObject()
            val c = j.optJSONObject("comando")
            // historico vem do mais recente para o mais antigo: o primeiro é o início do estado atual
            val inicio = j.optJSONArray("historico")?.optJSONObject(0)?.let { instante(it.texto("horaUtc")) }
            val criado = c?.let { instante(it.texto("criadoEmUtc")) }
            val desteAlerta = criado != null && (inicio == null || !criado.isBefore(inicio))
            return Resumo(
                estado = j.texto("estado", "SEM_DADOS"),
                fcMedia = if (r.isNull("fcMedia")) "—" else "${r.optDouble("fcMedia")} bpm",
                movimento = r.texto("movimento"),
                fonteMovimento = r.texto("fonteMovimento"),
                online = j.optBoolean("online"),
                ultimoContato = j.texto("ultimoContatoUtc"),
                comando = c?.let { "${it.texto("commandId")}: ${it.texto("status")}" },
                fcBpm = if (r.isNull("fcMedia") || !r.has("fcMedia")) "—"
                        else r.optDouble("fcMedia").roundToInt().toString(),
                statusComando = if (desteAlerta) c?.texto("status", "")?.ifEmpty { null } else null,
                comandoDesteAlerta = desteAlerta,
            )
        }
    }
}

// --- Apresentação: textos da tela, fora do Compose para serem testados ---

enum class Tom { BOM, ALERTA, NEUTRO }

data class Aparencia(val titulo: String, val descricao: String, val tom: Tom)

fun aparenciaDoEstado(estado: String): Aparencia = when (estado) {
    "NORMAL" -> Aparencia("Tudo bem", "Frequência cardíaca dentro do esperado", Tom.BOM)
    "ATENCAO" -> Aparencia("Atenção", "Frequência cardíaca alta com o paciente em repouso", Tom.ALERTA)
    "DADOS_INSUFICIENTES" -> Aparencia("Sem leituras suficientes", "Verifique o sensor e a conexão do dispositivo", Tom.NEUTRO)
    else -> Aparencia("Aguardando o dispositivo", "Ainda não chegaram leituras do paciente", Tom.NEUTRO)
}

fun textoMovimento(movimento: String): String = when (movimento) {
    "REST" -> "Em repouso"
    "ACTIVE" -> "Em movimento"
    "INVALIDO" -> "Leitura inválida"
    else -> "—"
}

fun textoComando(status: String?): String? = when (status) {
    null -> null
    "PENDENTE" -> "Enviado, aguardando o dispositivo"
    "ENTREGUE" -> "Entregue ao dispositivo"
    "EXECUTADO" -> "Alarme silenciado no dispositivo"
    else -> status
}

/** Instante de um horário ISO da API, ou null se ausente ou inválido. */
fun instante(iso: String): java.time.Instant? =
    try { OffsetDateTime.parse(iso).toInstant() } catch (e: Exception) { null }

/** Horário ISO da API (UTC) no fuso do celular, como HH:mm:ss; "—" se não houver. */
fun horaLocal(iso: String, fuso: ZoneId = ZoneId.systemDefault()): String = try {
    OffsetDateTime.parse(iso).atZoneSameInstant(fuso).format(DateTimeFormatter.ofPattern("HH:mm:ss"))
} catch (e: Exception) { "—" }
