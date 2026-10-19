"""PITUFO - PRUEBA 8.5 | Ajuste A/B del diagnostico de sobrecarga.

Repite exactamente el modelo de Prueba 08 (constantes estimadas, NO calibradas).
1) Genera mediciones con semillas de AJUSTE (810000+...)
2) Elige detector B entre candidatos solo con AJUSTE.
3) Compara detector A original y B elegido con semillas NUEVAS (910000+...).
4) Muestra reporte didactico ASCII y pregunta antes de crear CSV.

No confundir exito en simulacion con validacion de un motor real.
Solo biblioteca estandar. Disenado para Coding Python Android.
"""
import csv
import math
import os
import random
from datetime import datetime

# Parametros heredados de Prueba 08 (valores de trabajo, NO medidos)
V_OC, R_BAT, R_DRIVER = 12.0, 0.18, 0.565
R_M, L_M, KE, KT = 5.5, 0.025, 0.80, 0.63
J, B, T_FR, T_BASE = 0.018, 0.004, 0.025, 0.045
DT = 0.002
DURACION, INICIO, FIN = 18, 7, 11
REPETICIONES_AJUSTE = 10
REPETICIONES_VALIDACION = 10
MODO_EXPORTACION = 'PREGUNTAR'  # '0' para desactivar el menu

PERFILES = [
    ('01_NORMAL', 'normal', ()),
    ('02_DISPERSION', 'dispersion', ()),
    ('03_RUIDO_ALTO', 'ruido', ()),
    ('04_BATERIA_BAJA', 'bateria', ()),
    ('05_CARGA_BREVE', 'breve', ()),
    ('06_SOBRECARGA_LEVE_M1', 'leve', (0,)),
    ('07_SOBRECARGA_M1', 'fuerte', (0,)),
    ('08_SOBRECARGA_M2', 'fuerte', (1,)),
    ('09_SOBRECARGA_AMBOS', 'fuerte', (0, 1)),
    ('10_FALLA_RUIDO_BAJA', 'combinada', (0, 1)),
]

# Configuracion: (etiqueta, fraccion minima de rpm nominal, aumento de I, muestras)
ORIGINAL = ('A_ORIGINAL', 0.82, 0.14, 2)
CANDIDATOS = [
    ('B1_SUAVE', 0.86, 0.11, 2),
    ('B2_MEDIA', 0.88, 0.10, 2),
    ('B3_SENSIBLE', 0.90, 0.08, 2),
    ('B4_MUY_SENSIBLE', 0.92, 0.07, 2),
    ('B5_PERSISTENTE', 0.90, 0.08, 3),
]


class MotorDC:
    def __init__(self, r=R_M, ke=KE, kt=KT, j=J, b=B, fr=T_FR):
        self.r, self.ke, self.kt = r, ke, kt
        self.j, self.b, self.fr = j, b, fr
        self.i, self.w = 0.0, 0.0

    def paso(self, pwm, vbus, carga):
        if pwm == 0:
            # Simplificacion: giro libre / coast sin regeneracion
            self.i *= math.exp(-DT / 0.004)
        else:
            vmotor = vbus * pwm / 100.0
            di = (vmotor - (self.r + R_DRIVER) * self.i
                  - self.ke * self.w) / L_M
            self.i = max(0.0, self.i + di * DT)
        torque = self.kt * self.i
        resistencia = carga + self.b * self.w + self.fr
        self.w = max(0.0, self.w + (torque - resistencia) * DT / self.j)

    def rpm(self):
        return self.w * 60.0 / (2.0 * math.pi)


def unidad_realista(rng, perfil):
    dispersion = 0.08 if perfil in ('dispersion', 'combinada') else 0.03
    dispersion_j = 0.15 if perfil in ('dispersion', 'combinada') else 0.08

    def variar(x, porcentaje):
        return x * rng.uniform(1 - porcentaje, 1 + porcentaje)

    return MotorDC(r=variar(R_M, dispersion),
                   ke=variar(KE, dispersion),
                   kt=variar(KT, dispersion),
                   j=variar(J, dispersion_j),
                   b=variar(B, dispersion_j),
                   fr=variar(T_FR, dispersion_j))


def generar_telemetria(nombre, perfil, afectados, semilla):
    """Genera UNA misma secuencia de mediciones para todos los detectores."""
    rng = random.Random(semilla)
    motores = [unidad_realista(rng, perfil) for _ in range(2)]
    refs = [MotorDC(), MotorDC()]
    ruido_rpm = 4.0 if perfil in ('ruido', 'combinada') else 0.8
    ruido_amp = 0.035 if perfil in ('ruido', 'combinada') else 0.01
    bateria = 10.6 if perfil in ('bateria', 'combinada') else V_OC
    rbat = R_BAT * (1.30 if perfil in ('bateria', 'combinada') else 1.0)
    registros = []

    for segundo in range(1, DURACION + 1):
        pwm = 0 if (segundo == 1 or segundo >= 17) else 75
        periodo = INICIO <= segundo <= FIN
        breve = perfil == 'breve' and segundo == INICIO
        cargas = []
        for k in range(2):
            extra = 0.0
            if periodo and k in afectados:
                extra = 0.105 if perfil == 'leve' else 0.28
            if breve and k == 1:
                extra = 0.28
            cargas.append(max(0.0, T_BASE + rng.uniform(-0.003, 0.003) + extra))

        for _ in range(int(1.0 / DT)):
            vbus = max(8.5, bateria - rbat * sum(m.i for m in motores))
            for k in range(2):
                motores[k].paso(pwm, vbus, cargas[k])
                refs[k].paso(pwm, vbus, T_BASE)

        rpm = []
        corriente = []
        for k in range(2):
            rpm.append(max(0.0, motores[k].rpm() +
                           (rng.gauss(0, ruido_rpm) if pwm else 0.0)))
            corriente.append(max(0.0, motores[k].i + rng.gauss(0, ruido_amp)))

        registros.append({
            't': segundo, 'pwm': pwm, 'vbus': vbus,
            'rpm': rpm, 'amp': corriente,
            'ref_rpm': [m.rpm() for m in refs],
            'ref_amp': [m.i for m in refs],
            'falla': [bool(periodo and k in afectados) for k in range(2)],
            'breve': bool(breve),
        })
    return registros


def evaluar(registros, config, afectados, perfil):
    """El detector NO accede a la etiqueta de falla; solo el evaluador la usa."""
    nombre, factor_rpm, aumento_amp, confirmaciones = config
    contadores = [0, 0]
    vistos = [False, False]
    tiempos = [None, None]
    fuera = 0
    recuperacion = 0
    fuera_normal = 0
    advertencias_breve = 0
    estados = []

    for d in registros:
        actual = []
        for k in range(2):
            sospecha = (
                d['pwm'] >= 45 and d['ref_rpm'][k] >= 40 and
                d['rpm'][k] < factor_rpm * d['ref_rpm'][k] and
                d['amp'][k] > d['ref_amp'][k] + aumento_amp
            )
            contadores[k] = contadores[k] + 1 if sospecha else 0
            if contadores[k] >= confirmaciones:
                estado = 'ALERTA'
            elif contadores[k] > 0:
                estado = 'ADVERTENCIA'
            else:
                estado = 'NORMAL'
            actual.append(estado)

            # Etiquetas usadas EXCLUSIVAMENTE para puntuar, no para detectar.
            if estado == 'ALERTA':
                if d['falla'][k]:
                    vistos[k] = True
                    if tiempos[k] is None:
                        tiempos[k] = d['t']
                else:
                    fuera += 1
                    if k in afectados and FIN < d['t'] <= FIN + 2:
                        recuperacion += 1
                    else:
                        fuera_normal += 1
            if perfil == 'breve' and estado == 'ADVERTENCIA':
                advertencias_breve += 1
        estados.append(actual)

    esperados = len(afectados)
    detectados = sum(1 for k in afectados if vistos[k])
    latencias = [tiempos[k] - INICIO for k in afectados if tiempos[k] is not None]
    return {
        'esperados': esperados,
        'detectados': detectados,
        'omitidos': esperados - detectados,
        'fuera': fuera,
        'recuperacion': recuperacion,
        'fuera_normal': fuera_normal,
        'avisos_breve': advertencias_breve,
        'suma_latencias': sum(latencias),
        'n_latencias': len(latencias),
        'estados': estados,
    }


def agregar(acum, met):
    for campo in ('esperados', 'detectados', 'omitidos', 'fuera',
                  'recuperacion', 'fuera_normal', 'avisos_breve',
                  'suma_latencias', 'n_latencias'):
        acum[campo] += met[campo]


def acumulador():
    return {k: 0 for k in (
        'esperados', 'detectados', 'omitidos', 'fuera',
        'recuperacion', 'fuera_normal', 'avisos_breve',
        'suma_latencias', 'n_latencias')}


def construir_conjunto(base, repeticiones):
    """Mide el mismo modelo de Prueba 08, no recalibra motores."""
    casos = []
    for indice, (nombre, perfil, afectados) in enumerate(PERFILES):
        for j in range(repeticiones):
            semilla = base + indice * 1000 + j
            datos = generar_telemetria(nombre, perfil, afectados, semilla)
            casos.append((nombre, perfil, afectados, semilla, datos))
    return casos


def evaluar_lote(casos, config):
    resultado = acumulador()
    por_perfil = {}
    por_caso = []
    for nombre, perfil, afectados, semilla, datos in casos:
        met = evaluar(datos, config, afectados, perfil)
        agregar(resultado, met)
        if nombre not in por_perfil:
            por_perfil[nombre] = acumulador()
        agregar(por_perfil[nombre], met)
        por_caso.append((nombre, perfil, afectados, semilla, met))
    return resultado, por_perfil, por_caso


def puntuacion(resultado):
    # Penalizaciones elegidas ANTES de evaluar el conjunto de validacion.
    # Las alertas fuera de inyeccion en recuperacion se tratan aparte.
    return (50 * resultado['detectados']
            - 100 * resultado['fuera_normal']
            - 15 * resultado['recuperacion']
            - 2 * resultado['avisos_breve'])


def porcentaje(num, den):
    return (100.0 * num / den) if den else 0.0


def barra(pct, largo=20):
    bloques = max(0, min(largo, int(round(pct / 100 * largo))))
    return '[' + '#' * bloques + '.' * (largo - bloques) + ']'


def mostrar_detalle(nom, a, b):
    print('\n' + '=' * 55)
    print('VALIDACION: ' + nom)
    for k, config in (('A', a), ('B', b)):
        m = config
        sens = porcentaje(m['detectados'], m['esperados'])
        print('%s %s %5.1f%% (%d/%d)' % (
            k, barra(sens), sens, m['detectados'], m['esperados']))
    print('Fuera de inyeccion = muestras con alerta confirmada')
    print('NO equivale necesariamente a una falla falsa.')


def mostrar_tabla_perfiles(a, b):
    print('\nPOR PERFIL (validacion, semillas NUEVAS)')
    print('Perfil                     | A | B | alertas fuera A/B')
    print('-' * 62)
    for nombre, _, afectados in PERFILES:
        x, y = a[nombre], b[nombre]
        print('%-26s | %2d/%2d | %2d/%2d | %2d / %2d' % (
            nombre, x['detectados'], x['esperados'],
            y['detectados'], y['esperados'], x['fuera'], y['fuera']))


def ejemplo_visual(casos, conf_a, conf_b):
    # Demostracion de falla leve con una semilla reservada de validacion.
    elegido = next(c for c in casos if c[1] == 'leve')
    nombre, perfil, afectados, semilla, datos = elegido
    ea = evaluar(datos, conf_a, afectados, perfil)['estados']
    eb = evaluar(datos, conf_b, afectados, perfil)['estados']
    print('\n' + '=' * 55)
    print('APRENDIZAJE: FALLA LEVE, MISMAS MEDICIONES PARA A Y B')
    print('Semilla:', semilla, '| * = carga extra SOLO para verificacion')
    print('t  RPM M1  RPM ref  I M1  I ref | detector A  detector B')
    for j, d in enumerate(datos):
        if d['t'] in (5, 6, 7, 8, 9, 11, 12):
            print('%2d%s %6.1f  %6.1f  %5.3f  %5.3f | %-11s %-11s' % (
                d['t'], '*' if d['falla'][0] else ' ',
                d['rpm'][0], d['ref_rpm'][0],
                d['amp'][0], d['ref_amp'][0],
                ea[j][0], eb[j][0]))
    return elegido, ea, eb


def preguntar_exportacion():
    if MODO_EXPORTACION != 'PREGUNTAR':
        return MODO_EXPORTACION if MODO_EXPORTACION in ('1', '2', '3') else '0'
    print('\nEXPORTACION OPCIONAL: 0=Nada (predeterminado)')
    print('1=Resumen CSV | 2=Ejemplo detallado CSV | 3=Ambos')
    try:
        resp = input('Guardar archivos? [0/1/2/3]: ').strip()
    except (EOFError, OSError, RuntimeError):
        print('Entrada no disponible, no se generan archivos.')
        return '0'
    return resp if resp in ('1', '2', '3') else '0'


def exportar(filas, prefijo):
    if not filas:
        return
    destino = '/storage/emulated/0/Download'
    nombre = '%s_%s.csv' % (prefijo, datetime.now().strftime('%Y%m%d_%H%M%S'))
    try:
        ruta = os.path.join(destino, nombre)
        with open(ruta, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
            w.writeheader()
            w.writerows(filas)
        print('CSV GUARDADO:', ruta)
    except OSError as ex:
        print('No se pudo guardar CSV en Descargas:', ex)
        print('No se escribio ninguna copia en carpeta privada.')


def principal():
    print('PITUFO - PRUEBA 8.5 | COMPARACION A/B')
    print('Modelo fisico heredado de Prueba 08, SIN parametros medidos')
    print('Generando conjunto de AJUSTE...', flush=True)
    ajuste = construir_conjunto(810000, REPETICIONES_AJUSTE)

    print('\nAJUSTE (solo estas semillas eligen B)')
    opciones = []
    for c in CANDIDATOS:
        m, _, _ = evaluar_lote(ajuste, c)
        puntu = puntuacion(m)
        opciones.append((puntu, c, m))
        print('%-16s %2d/%2d detectados, %2d alerta-normal, '
              '%2d recuperacion, score=%d' % (
                  c[0], m['detectados'], m['esperados'],
                  m['fuera_normal'], m['recuperacion'], puntu))
    # Si hay empate, conservar la opcion mas conservadora (orden de la lista).
    mejor = max(opciones, key=lambda v: v[0])[1]
    print('SELECCIONADO:', mejor[0],
          '| umbral RPM=%.2f | delta I=%.2f A | muestras=%d' %
          (mejor[1], mejor[2], mejor[3]))

    print('\nGenerando VALIDACION INDEPENDIENTE...', flush=True)
    validacion = construir_conjunto(910000, REPETICIONES_VALIDACION)
    base, perfil_a, casos_a = evaluar_lote(validacion, ORIGINAL)
    nuevo, perfil_b, casos_b = evaluar_lote(validacion, mejor)
    mostrar_detalle('TOTAL', base, nuevo)
    mostrar_detalle('SOLO SOBRECARGA LEVE', perfil_a['06_SOBRECARGA_LEVE_M1'],
                    perfil_b['06_SOBRECARGA_LEVE_M1'])
    mostrar_tabla_perfiles(perfil_a, perfil_b)

    print('\nINDICADORES DE VALIDACION')
    for etiqueta, r in (('A (original)', base), ('B (ajustado)', nuevo)):
        latencia = (float(r['suma_latencias']) / r['n_latencias']
                    if r['n_latencias'] else None)
        print('%s: detectados %d/%d | omitidos %d | '
              'fuera_normal %d | en_recuperacion %d | latencia %s s' % (
                  etiqueta, r['detectados'], r['esperados'], r['omitidos'],
                  r['fuera_normal'], r['recuperacion'],
                  ('%.2f' % latencia) if latencia is not None else 'N/A'))

    ejemplo, estados_a, estados_b = ejemplo_visual(validacion, ORIGINAL, mejor)
    print('\nIMPORTANTE: son datos sinteticos. No hay validacion fisica.')
    print('Una sensibilidad superior puede aumentar falsas alertas.')
    print('La comparacion es justa: mismo PWM, ruido y motor para A/B.')

    opcion = preguntar_exportacion()
    if opcion in ('1', '3'):
        resumen = []
        for ca, cb in zip(casos_a, casos_b):
            nombre, perfil, afectados, semilla, x = ca
            y = cb[4]
            resumen.append({
                'perfil': nombre, 'semilla': semilla,
                'eventos_esperados': x['esperados'],
                'A_detectados': x['detectados'],
                'B_detectados': y['detectados'],
                'A_omitidos': x['omitidos'],
                'B_omitidos': y['omitidos'],
                'A_fuera_normal_muestras': x['fuera_normal'],
                'B_fuera_normal_muestras': y['fuera_normal'],
                'A_recuperacion_muestras': x['recuperacion'],
                'B_recuperacion_muestras': y['recuperacion'],
                'modelo_B_elegido': mejor[0],
            })
        exportar(resumen, 'pitufo_prueba085_resumen')
    if opcion in ('2', '3'):
        nom, perfil, afectados, semilla, registros = ejemplo
        detalle = []
        for j, d in enumerate(registros):
            detalle.append({
                'perfil': nom, 'semilla': semilla, 'segundo': d['t'],
                'pwm_pct': d['pwm'], 'v_bus_V': round(d['vbus'], 3),
                'rpm_m1': round(d['rpm'][0], 2),
                'rpm_ref_m1': round(d['ref_rpm'][0], 2),
                'corriente_m1_A': round(d['amp'][0], 3),
                'corriente_ref_m1_A': round(d['ref_amp'][0], 3),
                'falla_inyectada_m1': int(d['falla'][0]),
                'diagnostico_A': estados_a[j][0],
                'diagnostico_B': estados_b[j][0],
            })
        exportar(detalle, 'pitufo_prueba085_ejemplo')
    print('\nPRUEBA 8.5 COMPLETADA', flush=True)


if __name__ == '__main__':
    principal()
