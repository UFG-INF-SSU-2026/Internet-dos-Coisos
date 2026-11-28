package br.ufg.coisos

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class LoginScreenTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun mostraCamposDeLoginDoCuidador() {
        composeRule.onNodeWithText("Coisos Cuidador").assertIsDisplayed()
        composeRule.onNodeWithText("Servidor (https://)").assertIsDisplayed()
        composeRule.onNodeWithText("Usuário").assertIsDisplayed()
        composeRule.onNodeWithText("Senha").assertIsDisplayed()
        composeRule.onNodeWithText("Entrar").assertIsDisplayed()
    }

    @Test
    fun recusaUrlSemHostAntesDeFazerRequisicao() {
        // O formulário abre com o esquema incompleto "https://".
        composeRule.onNodeWithText("Entrar").performClick()
        composeRule.onNodeWithText("Use a URL https:// do túnel").assertIsDisplayed()
    }
}
