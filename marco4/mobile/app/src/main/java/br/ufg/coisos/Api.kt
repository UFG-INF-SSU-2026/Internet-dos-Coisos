package br.ufg.coisos

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Erro HTTP com o código, para a tela decidir (401 = login de novo). */
class ErroApi(val codigo: Int, mensagem: String) : IOException(mensagem)

/**
 * Cliente da API do Marco 4 (contrato em marco4/contrato/app-v1.json).
 *
 * Só aceita https://: a conexão é HttpsURLConnection e o Android valida o
 * certificado do túnel com as CAs do sistema. Nenhuma chave fica no APK;
 * o token vem do login e fica só em memória.
 */
class Api(baseUrl: String) {
    private val base = baseUrl.trim().trimEnd('/')

    init {
        require(base.startsWith("https://")) { "Use a URL https:// do túnel" }
    }

    var token: String? = null
        private set
    var paciente: String = ""
        private set

    suspend fun login(usuario: String, senha: String) {
        val resp = chamar("POST", "/api/app/login",
            JSONObject().put("usuario", usuario).put("senha", senha), autenticar = false)
        token = resp.getString("token")
        paciente = resp.getString("paciente")
    }

    suspend fun estado(): JSONObject = chamar("GET", "/api/pacientes/$paciente/estado")

    suspend fun reconhecerAlerta(): JSONObject = chamar("POST", "/api/pacientes/$paciente/comando")

    /** intensidade = |módulo da aceleração / 9,81 - 1|, em g; capturadoEmMs = hora da medida. */
    suspend fun enviarMovimento(intensidade: Double, capturadoEmMs: Long): JSONObject =
        chamar("POST", "/api/app/leituras", JSONObject()
            .put("entityId", paciente)
            .put("intensidade", intensidade.coerceIn(0.0, 8.0))
            .put("capturadoEmMs", capturadoEmMs))

    private suspend fun chamar(
        metodo: String, rota: String, corpo: JSONObject? = null, autenticar: Boolean = true,
    ): JSONObject = withContext(Dispatchers.IO) {
        val con = URL(base + rota).openConnection() as HttpURLConnection
        try {
            con.requestMethod = metodo
            con.connectTimeout = 5_000
            con.readTimeout = 10_000
            con.setRequestProperty("Accept", "application/json")
            if (autenticar) token?.let { con.setRequestProperty("Authorization", "Bearer $it") }
            if (corpo != null) {
                con.doOutput = true
                con.setRequestProperty("Content-Type", "application/json")
                con.outputStream.use { it.write(corpo.toString().toByteArray()) }
            }
            val codigo = con.responseCode
            val texto = (if (codigo < 400) con.inputStream else con.errorStream)
                ?.bufferedReader()?.use { it.readText() }.orEmpty()
            val json = if (texto.isBlank()) JSONObject() else JSONObject(texto)
            if (codigo >= 400) throw ErroApi(codigo, json.optString("erro", "HTTP $codigo"))
            json
        } finally {
            con.disconnect()
        }
    }
}
