package br.ufg.coisos

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class ErroApi(val codigo: Int, mensagem: String) : IOException(mensagem)

/** Cliente REST do Marco 4. Só aceita HTTPS; nenhuma chave fica dentro do APK. */
class Api(baseUrl: String) {
    private val base = urlDaApi(baseUrl)

    var token: String? = null
        private set
    var paciente: String = ""
        private set

    suspend fun login(usuario: String, senha: String) {
        val resp = chamar(
            "POST", "/api/app/login",
            JSONObject().put("usuario", usuario).put("senha", senha),
            autenticar = false,
        )
        token = resp.getString("token")
        paciente = resp.getString("paciente")
    }

    suspend fun estado(): JSONObject =
        chamar("GET", "/api/pacientes/$paciente/estado")

    suspend fun historico(limite: Int = 80): JSONObject =
        chamar("GET", "/api/pacientes/$paciente/historico?limite=${limite.coerceIn(1, 500)}")

    suspend fun reconhecerAlerta(): JSONObject =
        chamar("POST", "/api/pacientes/$paciente/comando")

    suspend fun enviarMovimento(intensidade: Double, capturadoEmMs: Long): JSONObject =
        chamar("POST", "/api/app/leituras", corpoMovimento(paciente, intensidade, capturadoEmMs))

    private suspend fun chamar(
        metodo: String,
        rota: String,
        corpo: JSONObject? = null,
        autenticar: Boolean = true,
    ): JSONObject = withContext(Dispatchers.IO) {
        val con = URL(base + rota).openConnection() as HttpURLConnection
        try {
            con.requestMethod = metodo
            con.connectTimeout = 5_000
            con.readTimeout = 10_000
            con.setRequestProperty("Accept", "application/json")
            if (autenticar) {
                token?.let { con.setRequestProperty("Authorization", "Bearer $it") }
            }
            if (corpo != null) {
                con.doOutput = true
                con.setRequestProperty("Content-Type", "application/json")
                con.outputStream.use { it.write(corpo.toString().toByteArray(Charsets.UTF_8)) }
            }

            val codigo = con.responseCode
            val texto = (if (codigo < 400) con.inputStream else con.errorStream)
                ?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val json = if (texto.isBlank()) JSONObject() else JSONObject(texto)
            if (codigo >= 400) throw ErroApi(codigo, json.optString("erro", "HTTP $codigo"))
            json
        } finally {
            con.disconnect()
        }
    }
}
