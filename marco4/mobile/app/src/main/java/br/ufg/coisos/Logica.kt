package br.ufg.coisos

import org.json.JSONObject
import kotlin.math.abs
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
) {
    /** O botão "Reconhecer alerta" só faz sentido com alerta ativo. */
    val podeReconhecer: Boolean get() = estado == "ATENCAO"

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
                comando = c?.let { "${it.texto("commandId")}: ${it.texto("status")}" },
            )
        }
    }
}
