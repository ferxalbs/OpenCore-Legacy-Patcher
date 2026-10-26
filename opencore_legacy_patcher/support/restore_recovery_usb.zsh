#!/bin/zsh
# Portable, explicit recovery of the original external OpenCore USB only.
# Copy this file into the kit's 07-Recuperacion-Portable directory.
set -eu
umask 077
ROOT="${0:A:h:h}"
IDENTITY="$ROOT/00-Estado/IDENTIDAD-PRIVADA.plist"
SOURCE="$ROOT/01-EFI-Actual"
MODE="${1:-actual}"
[[ "$MODE" == actual || "$MODE" == anterior || "$MODE" == --comprobar ]] || { print 'Modo no reconocido.'; exit 1; }
[[ -f "$IDENTITY" && -f "$SOURCE/VERIFICAR-EFI.sha256" ]] || { print 'Falta el inventario o el respaldo del kit.'; exit 1; }
get() { /usr/bin/plutil -extract "$1" raw -o - "$2"; }
PART="$(get usb_opencore_partition_uuid "$IDENTITY")"
VOLUME="$(get usb_opencore_volume_uuid "$IDENTITY")"
EXPECTED_SIZE="$(get usb_opencore_efi_size "$IDENTITY")"
if [[ "$MODE" != --comprobar && "$(/usr/bin/id -u)" != 0 ]]; then
  exec /usr/bin/sudo /bin/zsh "$0" "$MODE"
fi
TMP="$(/usr/bin/mktemp)"
MOUNT=''
DEVICE=''
RW=0
BACKUP=''
cleanup() {
  if (( RW )); then
    /bin/sync
    /usr/sbin/diskutil unmount "$DEVICE" >/dev/null || true
    /usr/sbin/diskutil mount readOnly "$DEVICE" >/dev/null || true
  fi
  /bin/rm -f "$TMP"
}
trap cleanup EXIT
refresh() {
  /usr/sbin/diskutil info -plist "$PART" > "$TMP"
  [[ "$(get DiskUUID "$TMP")" == "$PART" && "$(get VolumeUUID "$TMP")" == "$VOLUME" ]] || { print 'Identidad de EFI distinta.'; exit 1; }
  [[ "$(get Internal "$TMP")" == false && "$(get BusProtocol "$TMP")" == USB && "$(get Size "$TMP")" == "$EXPECTED_SIZE" ]] || { print 'El destino no es la EFI del USB externo esperado.'; exit 1; }
  DEVICE="$(get DeviceIdentifier "$TMP")"
  MOUNT="$(get MountPoint "$TMP")"
}
print 'Verificando todos los archivos de la EFI respaldada...'
(cd "$SOURCE" && /usr/bin/shasum -a 256 -c VERIFICAR-EFI.sha256 > /dev/null)
refresh
if [[ "$MODE" == --comprobar ]]; then
  print "Respaldo valido. Destino identificado: $DEVICE, EFI externa USB de $EXPECTED_SIZE bytes."
  print 'Modo de comprobacion: no se escribio ni monto la EFI.'
  exit 0
fi
if [[ -z "$MOUNT" ]]; then
  /usr/sbin/diskutil mount readOnly "$DEVICE" >/dev/null
  refresh
fi
[[ -d "$MOUNT" && "$MOUNT" != / && "$MOUNT" != /System/Volumes/Data ]] || { print 'Punto de montaje no permitido.'; exit 1; }
if [[ "$MODE" == anterior ]]; then
  [[ -f "$MOUNT/EFI/OC/OpenCore.efi" ]] || { print 'Falta OpenCore. Usa la restauracion de EFI completa.'; exit 1; }
  [[ "$(/usr/bin/shasum -a 256 "$MOUNT/EFI/OC/OpenCore.efi" | /usr/bin/awk '{print $1}')" == "$(/usr/bin/shasum -a 256 "$SOURCE/EFI/OC/OpenCore.efi" | /usr/bin/awk '{print $1}')" ]] || { print 'OpenCore es diferente. Revisar antes de restaurar solo el config.'; exit 1; }
  CONFIG="$SOURCE/Config-anterior-a-WiFi-Audio-nativos.plist"
  EXPECTED_CONFIG="$(get config_anterior_sha256 "$IDENTITY")"
else
  CONFIG="$SOURCE/EFI/OC/config.plist"
  EXPECTED_CONFIG="$(get config_actual_sha256 "$IDENTITY")"
fi
[[ "$(/usr/bin/shasum -a 256 "$CONFIG" | /usr/bin/awk '{print $1}')" == "$EXPECTED_CONFIG" ]] || { print 'Hash del config incorrecto.'; exit 1; }
/usr/bin/plutil -lint "$CONFIG"
STAMP="$(/bin/date +%Y%m%d-%H%M%S)"
BACKUP="$ROOT/07-Recuperacion-Portable/Antes-de-restaurar-$STAMP"
/bin/mkdir -p "$BACKUP"
if [[ -d "$MOUNT/EFI" ]]; then
  /usr/bin/ditto "$MOUNT/EFI" "$BACKUP/EFI"
else
  print 'El destino no contenia una carpeta EFI.' > "$BACKUP/ESTADO-ANTERIOR.txt"
fi
print "Destino verificado: $DEVICE. Copia anterior: $BACKUP"
/usr/sbin/diskutil unmount "$DEVICE" >/dev/null
/usr/sbin/diskutil mount "$DEVICE" >/dev/null
RW=1
refresh
[[ "$(get Writable "$TMP")" == true ]] || { print 'La EFI no permite escritura.'; exit 1; }
if [[ "$MODE" == actual ]]; then
  /usr/bin/ditto "$SOURCE/EFI" "$MOUNT/EFI"
  (cd "$MOUNT" && /usr/bin/shasum -a 256 -c "$SOURCE/VERIFICAR-EFI.sha256" > /dev/null)
else
  [[ ! -e "$MOUNT/EFI/OC/config.recovery-pending.plist" ]] || { print 'Existe un config pendiente no revisado.'; exit 1; }
  /bin/cp "$CONFIG" "$MOUNT/EFI/OC/config.recovery-pending.plist"
  /bin/mv "$MOUNT/EFI/OC/config.recovery-pending.plist" "$MOUNT/EFI/OC/config.plist"
fi
[[ "$(/usr/bin/shasum -a 256 "$MOUNT/EFI/OC/config.plist" | /usr/bin/awk '{print $1}')" == "$EXPECTED_CONFIG" ]] || { print 'La verificacion final fallo. No reiniciar.'; exit 1; }
/bin/sync
print 'Restauracion verificada. La EFI se dejara en solo lectura.'
print 'No se modificaron Windows, el arranque predeterminado ni los volumenes de macOS.'
print 'No se reinicia automaticamente. Prueba primero macOS (Sequoia) desde el mismo USB.'
