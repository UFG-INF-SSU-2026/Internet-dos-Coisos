package br.ufg.coisos

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.sqrt

/** Testes de unidade do app, na JVM: ./gradlew testDebugUnitTest */
class IntensidadeTest {
    private val g = GRAVIDADE.toFloat()

    @Test fun parado_de_pe_e_zero() =
        assertEquals(0.0, intensidadeMovimento(0f, 0f, g), 1e-6)

    @Test fun parado_inclinado_tambem_e_zero() {
        // a gravidade dividida entre dois eixos: o módulo continua 1 g
        val c = (GRAVIDADE / sqrt(2.0)).toFloat()
        assertEquals(0.0, intensidadeMovimento(c, 0f, c), 1e-6)
    }

    @Test fun queda_livre_e_um_g() =
        assertEquals(1.0, intensidadeMovimento(0f, 0f, 0f), 1e-9)

    @Test fun sacudida_do_ensaio_passa_do_limiar_de_repouso() {
        // mesmo valor do ensaio no emulador: (0, 15, 9,8) m/s² -> 0,83 g
        val i = intensidadeMovimento(0f, 15f, 9.8f)
        assertEquals(0.83, i, 0.01)
        assertTrue(i > 0.15)
    }

    @Test fun tremor_pequeno_fica_abaixo_do_limiar() =
        assertTrue(intensidadeMovimento(0.3f, 0.2f, g + 0.5f) <= 0.15)
}

class UrlTest {
    @Test fun aceita_https_e_tira_barra_e_espacos() =
        assertEquals("https://x.trycloudflare.com", urlDaApi("  https://x.trycloudflare.com/ "))

    @Test fun recusa_http() {
        val e = assertThrows(IllegalArgumentException::class.java) { urlDaApi("http://x.trycloudflare.com") }
        assertEquals("Use a URL https:// do túnel", e.message)
    }

    @Test fun recusa_vazio_e_so_o_esquema() {
        assertThrows(IllegalArgumentException::class.java) { urlDaApi("") }
        assertThrows(IllegalArgumentException::class.java) { urlDaApi("https://") }
    }

    @Test fun recusa_sem_esquema() {
        assertThrows(IllegalArgumentException::class.java) { urlDaApi("x.trycloudflare.com") }
    }
}

class CorpoMovimentoTest {
    @Test fun segue_o_contrato_app_v1() {
        val c = corpoMovimento("patient-0042", 0.42, 1764252000123)
        assertEquals(setOf("entityId", "intensidade", "capturadoEmMs"), c.keys().asSequence().toSet())
        assertEquals("patient-0042", c.getString("entityId"))
        assertEquals(0.42, c.getDouble("intensidade"), 1e-9)
        assertEquals(1764252000123, c.getLong("capturadoEmMs"))
    }

    @Test fun limita_a_intensidade_entre_0_e_8() {
        assertEquals(INTENSIDADE_MAX, corpoMovimento("p", 50.0, 0).getDouble("intensidade"), 0.0)
        assertEquals(0.0, corpoMovimento("p", -1.0, 0).getDouble("intensidade"), 0.0)
    }
}

class ResumoTest {
    @Test fun estado_completo_em_alerta() {
        val r = Resumo.de(JSONObject("""
            {"estado":"ATENCAO","online":true,"ultimoContatoUtc":"2026-11-27T18:19:27+00:00",
             "resumo":{"fcMedia":120.0,"movimento":"REST","fonteMovimento":"esp32"},
             "comando":{"commandId":"cmd-735a593a","status":"EXECUTADO"}}"""))
        assertEquals("ATENCAO", r.estado)
        assertEquals("120.0 bpm", r.fcMedia)
        assertEquals("REST", r.movimento)
        assertEquals("esp32", r.fonteMovimento)
        assertTrue(r.online)
        assertEquals("cmd-735a593a: EXECUTADO", r.comando)
        assertTrue(r.podeReconhecer)
    }

    @Test fun campos_nulos_viram_traco_e_nao_o_texto_null() {
        // defeito achado no ensaio do emulador: aparecia "Último contato: null"
        val r = Resumo.de(JSONObject("""
            {"estado":"SEM_DADOS","online":false,"ultimoContatoUtc":null,
             "resumo":{"fcMedia":null,"movimento":null,"fonteMovimento":null},"comando":null}"""))
        assertEquals("—", r.ultimoContato)
        assertEquals("—", r.fcMedia)
        assertEquals("—", r.movimento)
        assertEquals("—", r.fonteMovimento)
        assertNull(r.comando)
        assertFalse(r.online)
        assertFalse(r.podeReconhecer)
    }

    @Test fun resposta_vazia_nao_quebra() {
        val r = Resumo.de(JSONObject("{}"))
        assertEquals("SEM_DADOS", r.estado)
        assertEquals("—", r.fcMedia)
        assertFalse(r.podeReconhecer)
    }

    @Test fun contexto_do_celular_desativa_o_botao() {
        val r = Resumo.de(JSONObject("""
            {"estado":"NORMAL","online":true,
             "resumo":{"fcMedia":120.0,"movimento":"ACTIVE","fonteMovimento":"celular"}}"""))
        assertEquals("celular", r.fonteMovimento)
        assertFalse(r.podeReconhecer)
    }
}

class ApresentacaoTest {
    @Test fun cada_estado_tem_titulo_e_tom() {
        assertEquals(Aparencia("Tudo bem", "Frequência cardíaca dentro do esperado", Tom.BOM),
            aparenciaDoEstado("NORMAL"))
        assertEquals(Tom.ALERTA, aparenciaDoEstado("ATENCAO").tom)
        assertEquals("Atenção", aparenciaDoEstado("ATENCAO").titulo)
        assertEquals(Tom.NEUTRO, aparenciaDoEstado("DADOS_INSUFICIENTES").tom)
        assertEquals("Aguardando o dispositivo", aparenciaDoEstado("SEM_DADOS").titulo)
        assertEquals("Aguardando o dispositivo", aparenciaDoEstado("qualquer coisa").titulo)
    }

    @Test fun movimento_em_portugues() {
        assertEquals("Em repouso", textoMovimento("REST"))
        assertEquals("Em movimento", textoMovimento("ACTIVE"))
        assertEquals("—", textoMovimento("—"))
        assertEquals("Leitura inválida", textoMovimento("INVALIDO"))
    }

    @Test fun status_do_comando_explica_o_ciclo_2() {
        assertEquals("Enviado, aguardando o dispositivo", textoComando("PENDENTE"))
        assertEquals("Entregue ao dispositivo", textoComando("ENTREGUE"))
        assertEquals("Alarme silenciado no dispositivo", textoComando("EXECUTADO"))
        assertNull(textoComando(null))
    }

    @Test fun fc_arredondada_e_hora_local() {
        val r = Resumo.de(JSONObject("""
            {"estado":"ATENCAO","ultimoContatoUtc":"2026-11-27T18:19:27.5+00:00",
             "resumo":{"fcMedia":119.6},"comando":{"commandId":"c","status":"ENTREGUE"}}"""))
        assertEquals("120", r.fcBpm)
        assertEquals("ENTREGUE", r.statusComando)
        assertEquals("15:19:27", horaLocal(r.ultimoContato, java.time.ZoneOffset.ofHours(-3)))
        assertEquals("—", horaLocal("—"))
        assertEquals("—", Resumo.de(JSONObject("{}")).fcBpm)
    }
}
