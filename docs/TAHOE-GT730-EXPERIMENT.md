# Prueba separada de Tahoe en el equipo GT 730

Esta preparación corresponde al Hackintosh ASUS con Core i5-10400F, GT 730
GK208B (`10de:1287`), Wi-Fi Intel (`8086:43f0`) y SMBIOS iMac20,1. No es una
certificación de compatibilidad con Hackintosh ni una actualización del Sequoia
de trabajo. Windows y Sequoia se conservan.

Estado de esta preparación: volumen vacío creado, EFI Intel corregida instalada
y verificada, paquetes descargados y comprobados. El arranque con la nueva EFI
y la instalación de Tahoe siguen pendientes. Sequoia conserva OCLP 2.5.1 y sus
root patches anteriores.

## Sistema elegido y recursos

El catálogo de Software Update de Apple consultado el 25 de octubre de 2026
ofrece Tahoe **26.7.1 / 25G241**. El InstallAssistant completo ocupa
18.380.974.544 bytes. AppleDB proporciona el enlace HTTPS al CDN de Apple y el
SHA-1 `3ddcf86a385791c0dc7aca7c3f3f4adb2ca25f73`; la firma del paquete de Apple
debe comprobarse además del hash de descarga.

La aplicación publicada para la prueba es OCLP **3.0.0-rc.3**, una prerelease.
Nuestro fork parte de esa base con cambios posteriores. Los módulos de Kepler,
Metal 3802 y Modern Wireless revisados no difieren entre esa RC y el fork en
esta preparación. La RC utiliza PatcherSupportPkg 2.0.2; el fork utiliza 2.0.3.
La comprobación de recursos del fork se hizo con el DMG 2.0.3 verificado contra
el SHA-256 publicado por GitHub. No debe confundirse esa comprobación con la
validación de los recursos incluidos en la aplicación RC. Se comprobó también
el hash de su DMG 2.0.2, la firma de la aplicación y las mismas 28 rutas de
recursos. El paquete oficial RC pasó la firma y la comprobación de notarización.

La selección Kepler se comprobó con entradas de Tahoe 26.7.1 / Darwin 25.6.
La primera lectura de OCLP también seleccionó Modern Wireless porque confiaba
en el IOName falseado de la EFI. Las 28 rutas conjuntas estaban presentes tanto
en PatcherSupportPkg 2.0.3 como en los recursos 2.0.2 de la RC oficial; esto no
justifica aplicar parches Broadcom a la tarjeta física Intel. Kepler no requiere
MetallibSupportPkg ni KDK en las condiciones evaluadas. Añadir el parche de audio
sí cambia esos requisitos.

La validación completa del repositorio terminó con código 0, incluidos los
casos específicos GT 730 y 60 combinaciones de Darwin. La EFI candidata pasó
el ocvalidate incluido, versión 1.0.8. Su versión de OpenCore existente tiene
la cadena enmascarada; no se declara una identidad exacta del binario.

## Almacenamiento y recuperación

Se midieron 92,6 GB libres antes de las descargas. Se creó un volumen APFS vacío
llamado `Tahoe-Pruebas` en el contenedor de macOS, sin redimensionar Windows.
El propietario confirmó que sus documentos importantes tienen copia fuera del
disco interno. El volumen de prueba comparte espacio y dispositivo con Sequoia;
no sustituye esa copia de seguridad.

No se presenta una cuota del volumen inicial como límite garantizado para el
grupo System/Data que pueda crear el instalador. Debe vigilarse el espacio del
contenedor durante descarga, extracción e instalación. La primera cuenta de
Tahoe debe ser nueva, sin migración completa de aplicaciones ni documentos.
El instalador completo descargado pasó su SHA-1 de referencia y la firma de
Apple; su SHA-256 local es
`ca854f49dfdedbe78492c26d0e4172ee4d37573e2d375ca90c083d7615b6f48a`.

La extracción manual de InstallAssistant no se considera una aplicación lista:
Gatekeeper la rechazó por `resource envelope is obsolete (custom omit rules)`.
La firma del código con requisito de anclaje Apple sí pasó al omitir únicamente
la evaluación de recursos, pero ese resultado no equivale a aceptar la app en
Gatekeeper. No se retiraron firmas ni se modificaron controles de seguridad.
Se preparó la instalación estándar del paquete firmado de Apple; requiere
autenticación local y solo añade la aplicación instaladora. Su resultado y los
metadatos internos deben comprobarse antes de iniciar la instalación del sistema.

Las EFI, manifiestos de hashes y comandos de recuperación con identificadores
del dispositivo se conservan en la auditoría privada, fuera de GitHub. La
partición EFI del USB se identifica por su UUID de partición y se comprueba
también su UUID de volumen, conexión USB y condición externa. El UUID FAT del
volumen por sí solo no es suficiente: se observó el mismo UUID en la EFI de una
imagen de recursos montada. El instalador se niega a escribir si no coinciden
todos los identificadores previstos.

## Corrección de la detección Wi-Fi y candidata

La configuración de origen inyecta `IOName=pci14e4,43a0` en el dispositivo
`PciRoot(0x0)/Pci(0x14,0x3)`. El modo `anti_spoof=True` del detector de OCLP
confía en ese nombre y devuelve Broadcom. Sin embargo, los valores PCI
`vendor-id`/`device-id`, leídos sin esa sustitución, son **8086:43f0**. El
controlador realmente cargado en Sequoia es AirportItlwm 2.3.0. Una detección
basada solamente en el nombre falseado era insuficiente.

La primera candidata se instaló en el USB y se corrigió antes de arrancarla
al encontrar esta discrepancia. La corrección instalada se verificó de forma
independiente contra sus 134 archivos: los 124 archivos originales distintos
del config siguen idénticos. Su restauración y corrección
se controlan por hashes conocidos; no se sobrescribe una EFI de estado distinto.
La candidata corregida conserva OpenCore, ACPI, SMBIOS, argumentos, SIP y todos
los binarios originales, y cambia lo siguiente:

* mantiene AirportItlwm, IOSkywalkFamily e IO80211FamilyLegacy en Darwin 24;
* limita el bloqueo del IOSkywalkFamily nativo a Darwin 24;
* activa el itlwm 2.3.0 ya presente exclusivamente en Darwin 25;
* retira el IOName falso para que OCLP no seleccione Modern Wireless en Tahoe;
* utiliza HeliPort para seleccionar las redes en Tahoe, con su interfaz propia;
* deja los dos kexts Broadcom añadidos en la primera preparación sin referencias
  activas en el config corregido. No se interpretan como controladores necesarios.

Retirar IOName también corrige la identificación que verá OCLP en Sequoia.
Sus parches ya instalados se conservan, pero una futura reinstalación de parches
Wi-Fi de Sequoia debe revisarse: esa instalación usa AirportItlwm con el stack
antiguo y el detector original dependía del nombre falseado. El config conocido
que arranca y conserva ese comportamiento sigue respaldado. Primero debe
comprobarse Sequoia con la candidata corregida; después se instala Tahoe.

itlwm utiliza IOEthernetController en lugar del stack privado IO80211Family.
Su entrada IOPCIPrimaryMatch acepta dispositivos Intel mediante máscara de
fabricante; esto por sí solo no certifica la inicialización del adaptador.
Los dos archivos de itlwm de la EFI coinciden exactamente con el ZIP de la
publicación oficial 2.3.0. HeliPort 1.5.0 procede de su publicación oficial;
el ejecutable x86_64 no está firmado. No se ha modificado ni firmado localmente.
La conexión, velocidad y reactivación deben probarse en Tahoe. No se promete
AirDrop ni equivalencia con el menú Wi-Fi nativo de AirportItlwm.

## Audio y límites de la prueba

El audio analógico actual utiliza Realtek ALC897 (`10ec:0897`) con AppleALC.
Tahoe eliminó AppleHDA; conservar AppleALC no restaura por sí solo el audio.
OCLP incluye AppleHDA de Tahoe beta 1, pero `ModernAudio.present()` no selecciona
ese parche para el SMBIOS iMac20,1, cuyo modelo Apple original tiene T2. El
Hackintosh no reproduce ese hardware. El recurso de audio se preparó aparte,
sin inyectarlo ni modificar los parches del Sequoia instalado.

Se descargó el KDK exacto 25G241 y se comprobó contra el SHA-256 del manifiesto
de Dortania. Se conserva sin instalar en Sequoia.

Restaurar audio mediante el parche Modern Audio requiere KDK en Tahoe, a
diferencia de los dos patchsets gráficos/red comprobados arriba. Debe resolverse
con evidencia del Tahoe arrancado y un mecanismo de selección explícito; no se
debe cambiar el SMBIOS a otro Mac para forzar múltiples parches ajenos al equipo.

El mapa USB actual es preliminar. Arranque, teclado/ratón, red, aceleración,
audio y reposo requieren comprobaciones reales. No se promete Mac2, nueva
decodificación por hardware, más FPS ni la desaparición de los cierres de
agentes de texto. El `revblock=auto,media` verificado en Sequoia se conserva.

Nunca ejecutar `--prepare_for_update`, desinstalar parches o aplicar root
patching desde Sequoia para preparar este experimento. Los parches de Tahoe se
aplican después de arrancar Tahoe y confirmar su versión y volumen de origen.
Los USB de recuperación de Sequoia y Windows se mantienen.

## Fuentes primarias y metadatos

* [OCLP 3.0.0-rc.3](https://github.com/dortania/OpenCore-Legacy-Patcher/releases/tag/3.0.0-rc.3)
* [Estado oficial de soporte Tahoe](https://github.com/dortania/OpenCore-Legacy-Patcher/issues/1167)
* [PatcherSupportPkg 2.0.3](https://github.com/dortania/PatcherSupportPkg/releases/tag/2.0.3)
* [Apple: instalar más de un macOS](https://support.apple.com/en-us/118282)
* [Apple: descargar e instalar macOS](https://support.apple.com/en-us/102662)
* [OpenIntelWireless: itlwm y HeliPort](https://openintelwireless.github.io/itlwm/FAQ.html)
* [HeliPort 1.5.0](https://github.com/OpenIntelWireless/HeliPort/releases/tag/v1.5.0)
* [AppleALC: limitación de AppleHDA en Tahoe](https://github.com/acidanthera/AppleALC)
* [Guía Tahoe de Dortania](https://github.com/dortania/OpenCore-Install-Guide/blob/master/extras/tahoe.md)
* [AppleDB: metadatos de instaladores usados por OCLP](https://api.appledb.dev/ios/macOS/main.json)
