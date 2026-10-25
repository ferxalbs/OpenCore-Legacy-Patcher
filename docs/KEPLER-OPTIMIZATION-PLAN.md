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

Se preparó una copia privada completa de la EFI inspeccionada, fuera del
repositorio. La EFI de arranque y los parches instalados permanecen intactos.

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

- nuevos incidentes GPU y sus procesos asociados, evitando contar varios
  informes del mismo incidente como reinicios independientes;
- síntomas durante navegación, desarrollo, vídeo e inactividad;
- continuidad de WindowServer y salida verificada de pequeñas pruebas Metal;
- presión de memoria y VRAM en cargas comparables.

El fallo de nsattributedstringagent, la decodificación de vídeo y el mapa USB
mantienen investigaciones separadas. Migrar a Tahoe sería otra prueba con
sus propios parches; la captura no establece que vaya a rendir mejor que
Sequoia en nuestro hardware. El candidato aún no se ha activado ni arrancado.
