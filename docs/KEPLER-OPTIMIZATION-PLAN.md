# Optimización de la GT 730 y comparación con Tahoe

## Aclaración de compatibilidad

Kepler tiene una ruta de compatibilidad en OCLP, incluida la rama 3.0.0 para
Tahoe. La incompatibilidad documentada en la investigación de NullMoth se
refiere a su controlador GSP; no significa que Kepler no pueda funcionar en
Tahoe mediante OCLP.

La captura aportada muestra una GT 710 en un escritorio que identifica el
sistema como Tahoe. Es compatible con esa ruta de OCLP, pero no prueba por sí
sola aceleración completa, rendimiento ni estabilidad prolongada. En nuestro
equipo sí se verificó una operación Metal pequeña sobre la GT 730 de Sequoia.

## Comparación reproducida desde el código

Se generaron los diccionarios de parches de `NvidiaKepler` para el dispositivo
`10de:1287`. El caso Sequoia usa 15.7.7 / Darwin 24.6. El caso Tahoe usa Darwin
25.0 y un build sintético, exclusivamente para examinar las decisiones del
código; no representa un sistema instalado ni una prueba de arranque.

| Componente seleccionado | Sequoia | Tahoe |
| --- | --- | --- |
| GeForce.kext | `12.0 Beta 6-23.4` | `12.0 Beta 6-23.4` |
| GeForceMTLDriver.bundle | `11.0 Beta 3-22` | `11.0 Beta 3-22` |
| Metal.framework | `13.2.1-24` | `13.2.1-25` |
| MTLCompiler.framework | `14.2 Beta 1` | `13.6-25` |
| GPUCompiler.framework | `11.6` | `13.2.1-25` |
| MetallibSupportPkg requerido por esta clase | Sí | No; usa otro conjunto de recursos |

Tahoe también selecciona reemplazos específicos de ImageIO, CMPhoto y el perfil
de sandbox de `nsattributedstringagent`. La coincidencia del nombre del agente
con nuestros informes no demuestra que ese parche de Tahoe corrija la causa
de los cierres de Sequoia. No se portó ese perfil ni se mezclaron frameworks
de distintas versiones de macOS.

Los resultados están en
[research/kepler-sequoia-tahoe-comparison.json](research/kepler-sequoia-tahoe-comparison.json).
La fuente correspondiente es
[nvidia_kepler.py](../opencore_legacy_patcher/sys_patch/patchsets/hardware/graphics/nvidia_kepler.py)
y [metal_3802.py](../opencore_legacy_patcher/sys_patch/patchsets/shared_patches/metal_3802.py).

## Primera configuración candidata

La preparación inicial conservó una copia privada completa de la EFI
inspeccionada, fuera del repositorio. El 25 de octubre de 2026 se instaló
únicamente el config candidato en la EFI USB existente; su prueba de arranque
sigue pendiente. Los parches de volumen raíz permanecen en OCLP 2.5.1.

Los únicos cambios del config candidato son:

1. Añadir `revblock=auto,media` a los argumentos existentes. `auto` conserva el
   comportamiento predeterminado de RestrictEvents y `media` bloquea
   mediaanalysisd. Se comprobó que no había otro revblock en el config y que
   RestrictEvents estaba habilitado.
2. Añadir `HideVerbose=false` a las cuatro entradas de controladores donde
   faltaba. Es una normalización de esquema para el validador incluido; no se
   presenta como una mejora de rendimiento gráfico.

Una comparación de los plist comprobó que todos los demás valores quedaron
iguales. No se sustituyeron binarios, tablas ACPI ni datos de identidad.
ocvalidate 1.0.8 aprobó el candidato con código 0. La identidad exacta de la
versión de OpenCore sigue sin establecerse porque su cadena está enmascarada.
La validación no sustituye una prueba física de arranque y recuperación.

La receta sin datos personales está en
[research/gt730-sequoia-stability-profile.json](research/gt730-sequoia-stability-profile.json).
El config real no se publica porque contiene identificadores del equipo.

## Medición pendiente

La finalidad del primer cambio es reducir los fallos ligados al análisis de
contenido, no incrementar una cifra de FPS. El propietario confirmó que no
utiliza las funciones de Fotos y Live Text afectadas.

Cuando se active una copia candidata con recuperación disponible, comparar:

* nuevos incidentes GPU y sus procesos asociados, evitando contar varios
  informes del mismo incidente como reinicios independientes;
* síntomas durante navegación, desarrollo, vídeo e inactividad;
* continuidad de WindowServer y salida verificada de pequeñas pruebas Metal;
* presión de memoria y VRAM en cargas comparables.

El fallo de nsattributedstringagent, la decodificación de vídeo y el mapa USB
mantienen investigaciones separadas. Migrar a Tahoe sería otra prueba con
sus propios parches; la captura no establece que vaya a rendir mejor que
Sequoia en nuestro hardware. El config candidato está instalado en la EFI USB; su efecto sigue pendiente
del próximo arranque de macOS y de las comprobaciones posteriores.

## Instalación y comprobación del 25 de octubre de 2026

El propietario informó que Windows volvió a funcionar y solicitó retomar la
adaptación de macOS. Una inspección nueva confirmó Sequoia 15.7.7 y la misma
EFI de 125 archivos que el respaldo anterior. RestrictEvents 1.1.7 estaba
cargado, sin `revblock`; una prueba Metal de 4096 bytes volvió a completarse.
Los 40 informes GPU recientes examinados mencionaban `mediaanalysisd`; varios
informes pueden pertenecer al mismo incidente y no se cuentan como 40 reinicios.

Con un respaldo completo recién verificado, se instaló el config revisado en
la EFI del USB. La comprobación independiente confirmó los cinco cambios
previstos, los otros 124 archivos idénticos y una copia adicional del config
original. La EFI quedó montada en solo lectura y el config instalado pasó
ocvalidate 1.0.8. La identidad exacta del OpenCore con versión enmascarada sigue
sin establecerse; validar el esquema no certifica el arranque.

Los argumentos de la sesión que ejecutó la instalación seguían sin `revblock`,
como corresponde antes de reiniciar. No se declara aún estabilidad mejorada.
En el próximo arranque, comprobar el argumento efectivo, RestrictEvents
cargado, una operación Metal y nuevos informes GPU durante uso normal e
inactividad. Los metadatos de root patch continuaban indicando OCLP 2.5.1 /
PatcherSupportPkg 1.9.7. Esta instalación no sustituyó esos recursos ni modificó
la EFI interna de Microsoft, ACPI, kexts o SMBIOS. Los originales y las rutas
específicas de recuperación permanecen en el respaldo privado del propietario.
