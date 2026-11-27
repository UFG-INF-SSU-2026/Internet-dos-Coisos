package br.ufg.coisos

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.sqrt

const val GRAVIDADE = 9.80665
const val INTENSIDADE_MAX = 8.0

fun intensidadeMovimento(x: Float, y: Float, z: Float): Double {
    val modulo = sqrt((x * x + y * y + z * z).toDouble())
    return abs(modulo / GRAVIDADE - 1.0)
}

fun urlDaApi(digitada: String): String {
    val base = digitada.trim().trimEnd('/')
    require(base.startsWith("https://") && base.length > "https://".length) {
        "Use a URL https:// do túnel"
    }
    return base
}

fun corpoMovimento(paciente: String, intensidade: Double, capturadoEmMs: Long): JSONObject =
    JSONObject()
        .put("entityId", paciente)
        .put("intensidade", intensidade.coerceIn(0.0, INTENSIDADE_MAX))
        .put("capturadoEmMs", capturadoEmMs)

fun JSONObject.texto(chave: String, padrao: String = "—"): String =
    if (isNull(chave) || !has(chave)) padrao else optString(chave, padrao)

private fun JSONObject.numero(chave: String): Double? {
    if (isNull(chave) || !has(chave)) return null
    return optDouble(chave).takeIf { it.isFinite() }
}

private fun JSONObject.listaObjetos(chave: String): List<JSONObject> {
    val array: JSONArray = optJSONArray(chave) ?: return emptyList()
    return buildList {
        for (i in 0 until array.length()) {
            array.optJSONObject(i)?.let(::add)
        }
    }
}

data class LeituraGrafico(
    val fc: Double?,
    val recebidoEmUtc: String = "—",
    val loteId: String = "—",
)

data class EventoEstado(
    val horaUtc: String,
    val estado: String,
    val razao: String,
)

data class LoteFila(
    val loteId: String,
    val origem: String,
)

fun leiturasDoHistorico(resposta: JSONObject): List<LeituraGrafico> =
    resposta.listaObjetos("leituras").map { item ->
        LeituraGrafico(
            fc = item.numero("fc"),
            recebidoEmUtc = item.texto("recebidoEmUtc"),
            loteId = item.texto("loteId"),
        )
    }

data class Resumo(
    val estado: String,
    val fcMedia: String,
    val fcMediaValor: Double?,
    val movimento: String,
    val fonteMovimento: String,
    val movimentoEsp32: String,
    val movimentoCelular: String,
    val coberturaFc: String,
    val coberturaMov: String,
    val online: Boolean,
    val ultimoContato: String,
    val lotesRecebidos: Int,
    val filaPendentes: Int,
    val filaEnfileirados: Int,
    val filaProcessados: Int,
    val capacidadeFila: Int,
    val ultimosLotes: List<LoteFila>,
    val historico: List<EventoEstado>,
    val leiturasRecentes: List<LeituraGrafico>,
    val persistencia: String,
    val erroPersistencia: String?,
    val gravacoesNaoPersistidas: Int,
    val celularUltimaLeitura: String,
    val celularRecebidas: Int,
    val celularDescartadas: Int,
    val comandoId: String?,
    val comandoStatus: String?,
    val comandoConfirmadoEm: String?,
) {
    val podeReconhecer: Boolean
        get() = estado == "ATENCAO" && (comandoStatus == null || comandoStatus == "EXECUTADO")

    val comando: String?
        get() = comandoStatus?.let { "${comandoId ?: "comando"}: $it" }

    companion object {
        fun de(j: JSONObject): Resumo {
            val r = j.optJSONObject("resumo") ?: JSONObject()
            val fila = j.optJSONObject("fila") ?: JSONObject()
            val celular = j.optJSONObject("celular") ?: JSONObject()
            val comando = j.optJSONObject("comando")
            val fc = r.numero("fcMedia")
            val coberturaFc = r.numero("coberturaFc")
            val coberturaMov = r.numero("coberturaMov")

            return Resumo(
                estado = j.texto("estado", "SEM_DADOS"),
                fcMedia = fc?.let { "%.1f bpm".format(java.util.Locale.ROOT, it) } ?: "—",
                fcMediaValor = fc,
                movimento = r.texto("movimento"),
                fonteMovimento = r.texto("fonteMovimento"),
                movimentoEsp32 = r.texto("movimentoEsp32"),
                movimentoCelular = r.texto("movimentoCelular"),
                coberturaFc = coberturaFc?.let { "${(it * 100).roundToInt()}%" } ?: "—",
                coberturaMov = coberturaMov?.let { "${(it * 100).roundToInt()}%" } ?: "—",
                online = j.optBoolean("online"),
                ultimoContato = j.texto("ultimoContatoUtc"),
                lotesRecebidos = j.optInt("lotesRecebidos"),
                filaPendentes = fila.optInt("pendentes"),
                filaEnfileirados = fila.optInt("enfileirados"),
                filaProcessados = fila.optInt("processados"),
                capacidadeFila = fila.optInt("capacidade", 128),
                ultimosLotes = fila.listaObjetos("ultimosLotesProcessados").map {
                    LoteFila(it.texto("loteId"), it.texto("origem"))
                },
                historico = j.listaObjetos("historico").map {
                    EventoEstado(it.texto("horaUtc"), it.texto("estado"), it.texto("razao"))
                },
                leiturasRecentes = j.listaObjetos("historicoLeituras").map {
                    LeituraGrafico(it.numero("fc"), it.texto("recebidoEmUtc"), it.texto("loteId"))
                },
                persistencia = j.texto("persistenciaTemporal", "não configurada"),
                erroPersistencia = if (j.isNull("erroPersistencia")) null else j.texto("erroPersistencia"),
                gravacoesNaoPersistidas = j.optInt("gravacoesNaoPersistidas"),
                celularUltimaLeitura = celular.texto("ultimaLeituraUtc"),
                celularRecebidas = celular.optInt("recebidas"),
                celularDescartadas = celular.optInt("descartadas"),
                comandoId = comando?.texto("commandId"),
                comandoStatus = comando?.texto("status"),
                comandoConfirmadoEm = comando?.let {
                    if (it.isNull("confirmadoEmUtc")) null else it.texto("confirmadoEmUtc")
                },
            )
        }
    }
}
