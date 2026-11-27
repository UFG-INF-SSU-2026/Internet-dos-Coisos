package br.ufg.coisos

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager

/**
 * Acelerômetro do celular: guarda o maior desvio de 1 g desde a última coleta.
 *
 * Usa o pico (e não a média) para que uma sacudida curta entre os envios de 2 s
 * não se perca. Mesma convenção do MPU6050 no ESP32: até 0,15 g = repouso.
 */
class Movimento(context: Context) : SensorEventListener {
    private val gerenciador = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val sensor: Sensor? = gerenciador.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)

    @Volatile private var pico = 0.0
    @Volatile private var teveLeitura = false

    val disponivel: Boolean get() = sensor != null

    fun iniciar() {
        sensor?.let { gerenciador.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
    }

    fun parar() = gerenciador.unregisterListener(this)

    /** Intensidade (g) acumulada desde a última chamada, ou null se o sensor não mandou nada. */
    fun coletar(): Double? {
        if (!teveLeitura) return null
        val valor = pico
        pico = 0.0
        teveLeitura = false
        return valor
    }

    override fun onSensorChanged(evento: SensorEvent) {
        val desvio = intensidadeMovimento(evento.values[0], evento.values[1], evento.values[2])
        if (desvio > pico) pico = desvio
        teveLeitura = true
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
}
