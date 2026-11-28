package br.ufg.coisos

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.sqrt

class IntensidadeTest {
    private val g = GRAVIDADE.toFloat()

    @Test fun parado_de_pe_e_zero() =
        assertEquals(0.0, intensidadeMovimento(0f, 0f, g), 1e-6)

    @Test fun parado_inclinado_tambem_e_zero() {
        val c = (GRAVIDADE / sqrt(2.0)).toFloat()
        assertEquals(0.0, intensidadeMovimento(c, 0f, c), 1e-6)
    }

    @Test fun queda_livre_e_um_g() =
        assertEquals(1.0, intensidadeMovimento(0f, 0f, 0f), 1e-9)

    @Test fun sacudida_do_ensaio_passa_do_limiar_de_repouso() {
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
        val e = assertThrows(IllegalArgumentException::class.java) {
            urlDaApi("http://x.trycloudflare.com")
        }
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

    @Test fun painel_expoe_cobertura_fila_persistencia_e_historico() {
        val r = Resumo.de(JSONObject("""
            {
              "estado":"ATENCAO","online":true,"lotesRecebidos":12,
              "resumo":{"fcMedia":121.25,"movimento":"REST","fonteMovimento":"esp32",
                        "movimentoEsp32":"REST","movimentoCelular":"REST",
                        "coberturaFc":0.8,"coberturaMov":1.0},
              "fila":{"pendentes":2,"enfileirados":14,"processados":12,"capacidade":128,
                      "ultimosLotesProcessados":[{"loteId":"lote-10","origem":"esp32"}]},
              "historico":[{"horaUtc":"2026-11-27T18:19:27+00:00","estado":"ATENCAO","razao":"condicao_persistiu"}],
              "historicoLeituras":[{"fc":121.0,"recebidoEmUtc":"2026-11-27T18:19:27+00:00","loteId":"lote-10"}],
              "persistenciaTemporal":"TimescaleDB","gravacoesNaoPersistidas":1,
              "celular":{"ultimaLeituraUtc":"2026-11-27T18:19:28+00:00","recebidas":9,"descartadas":1},
              "comando":{"commandId":"cmd-a","status":"ENTREGUE"}
            }"""))
        assertEquals("80%", r.coberturaFc)
        assertEquals("100%", r.coberturaMov)
        assertEquals(12, r.lotesRecebidos)
        assertEquals(2, r.filaPendentes)
        assertEquals(128, r.capacidadeFila)
        assertEquals("lote-10", r.ultimosLotes.single().loteId)
        assertEquals("ATENCAO", r.historico.single().estado)
        assertEquals(121.0, r.leiturasRecentes.single().fc!!, 0.0)
        assertEquals("TimescaleDB", r.persistencia)
        assertEquals(1, r.gravacoesNaoPersistidas)
        assertEquals(9, r.celularRecebidas)
        assertEquals("ENTREGUE", r.comandoStatus)
        assertFalse(r.podeReconhecer)
    }

    @Test fun reconhecimento_so_habilita_quando_nao_ha_comando_aberto() {
        val pendente = Resumo.de(JSONObject("""
            {"estado":"ATENCAO","comando":{"commandId":"cmd-a","status":"PENDENTE"}}"""))
        val entregue = Resumo.de(JSONObject("""
            {"estado":"ATENCAO","comando":{"commandId":"cmd-a","status":"ENTREGUE"}}"""))
        val executado = Resumo.de(JSONObject("""
            {"estado":"ATENCAO","comando":{"commandId":"cmd-a","status":"EXECUTADO"}}"""))
        val semComando = Resumo.de(JSONObject("""{"estado":"ATENCAO"}"""))
        assertFalse(pendente.podeReconhecer)
        assertFalse(entregue.podeReconhecer)
        assertTrue(executado.podeReconhecer)
        assertTrue(semComando.podeReconhecer)
    }

    @Test fun historico_persistido_converte_leituras() {
        val resposta = JSONObject("""
            {"origem":"TimescaleDB","leituras":[
              {"fc":98.5,"recebidoEmUtc":"2026-11-27T18:19:27+00:00","loteId":"lote-1"},
              {"fc":null,"recebidoEmUtc":"2026-11-27T18:19:30+00:00","loteId":"lote-2"}]}
        """)
        val leituras = leiturasDoHistorico(resposta)
        assertEquals(2, leituras.size)
        assertEquals(98.5, leituras.first().fc!!, 0.0)
        assertNull(leituras.last().fc)
        assertEquals("lote-2", leituras.last().loteId)
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
             "resumo":{"fcMedia":119.6},"comando":{"commandId":"c","status":"EXECUTADO"}}"""))
        assertEquals("120", r.fcBpm)
        assertNull(r.statusComando)              // executado e sem horário de criação: não é deste alerta
        assertEquals("15:19:27", horaLocal(r.ultimoContato, java.time.ZoneOffset.ofHours(-3)))
        assertEquals("—", horaLocal("—"))
        assertEquals("—", Resumo.de(JSONObject("{}")).fcBpm)
    }
}

class ComandoDoAlertaTest {
    private fun estado(inicio: String, criado: String?, status: String = "EXECUTADO") = Resumo.de(JSONObject("""
        {"estado":"ATENCAO","historico":[{"estado":"ATENCAO","horaUtc":"$inicio"}],
         "comando":${if (criado == null) "null" else """{"commandId":"c","status":"$status","criadoEmUtc":"$criado"}"""}}"""))

    @Test fun reconhecido_neste_alerta_esconde_o_botao_e_mostra_o_status() {
        val r = estado("2026-11-27T21:50:08+00:00", "2026-11-27T21:50:18+00:00")
        assertFalse(r.podeReconhecer)
        assertEquals("EXECUTADO", r.statusComando)
    }

    @Test fun comando_de_um_alerta_anterior_nao_aparece() {
        // defeito achado no ensaio completo: o alerta novo mostrava "Alarme silenciado"
        val r = estado("2026-11-27T21:56:16+00:00", "2026-11-27T21:50:18+00:00")
        assertTrue(r.podeReconhecer)
        assertNull(r.statusComando)
    }

    @Test fun pendente_neste_alerta_tambem_esconde_o_botao() {
        val r = estado("2026-11-27T21:50:08+00:00", "2026-11-27T21:50:18+00:00", "PENDENTE")
        assertFalse(r.podeReconhecer)
        assertEquals("PENDENTE", r.statusComando)
    }

    @Test fun comando_em_andamento_aparece_mesmo_sem_horario() {
        // regra do #6: com PENDENTE/ENTREGUE o botão fica bloqueado e o status aparece
        val r = Resumo.de(JSONObject("""{"estado":"ATENCAO","comando":{"commandId":"c","status":"ENTREGUE"}}"""))
        assertFalse(r.podeReconhecer)
        assertEquals("ENTREGUE", r.statusComando)
    }

    @Test fun sem_comando_pode_reconhecer() =
        assertTrue(estado("2026-11-27T21:50:08+00:00", null).podeReconhecer)
}
