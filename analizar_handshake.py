"""Diagnostico de handshake TCP 443 a partir de Pktmon pcapng, sin red.

No necesita Wireshark ni dependencias externas. Solo inspecciona cabeceras,
no imprime IP de visitantes ni datos del paquete. No modifica ServerTec.
Una captura local no acredita disponibilidad publica de Chrome/HTTPS.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import struct
import sys

SERVER_V4 = '198.51.100.10'
SERVER_V6 = '2001:db8:feed::10'
MAX_CAPTURE_BYTES = 16 * 1024 * 1024
MAX_BLOCK_COUNT = 100_000
MAX_TCP_PACKET_COUNT = 100_000
SYN, ACK, RST, FIN = 0x02, 0x10, 0x04, 0x01
LINK_ETHERNET, LINK_RAW, LINK_IPV4, LINK_IPV6 = 1, 101, 228, 229


@dataclass(frozen=True)
class TcpPacket:
    source: str
    destination: str
    source_port: int
    destination_port: int
    sequence: int
    acknowledgement: int
    flags: int
    ip_version: int


def _parse_tcp(raw: bytes, offset: int, source: str, destination: str,
               version: int) -> TcpPacket | None:
    if offset + 20 > len(raw):
        return None
    source_port, destination_port, seq, ack, encoded_offset, flags = struct.unpack_from(
        '!HHIIBB', raw, offset
    )
    tcp_header_length = (encoded_offset >> 4) * 4
    if tcp_header_length < 20 or source_port != 443 and destination_port != 443:
        return None
    # Only flags and sequence/acknowledgment numbers are used; payload is ignored.
    return TcpPacket(source, destination, source_port, destination_port,
                     seq, ack, flags, version)


def _ipv4(raw: bytes, pos: int) -> TcpPacket | None:
    if pos + 20 > len(raw) or raw[pos] >> 4 != 4:
        return None
    ihl = (raw[pos] & 15) * 4
    if ihl < 20 or pos + ihl + 20 > len(raw) or raw[pos + 9] != 6:
        return None
    fragment = struct.unpack_from('!H', raw, pos + 6)[0]
    if fragment & 0x1FFF:
        return None  # No TCP header in noninitial IPv4 fragments.
    total_len = struct.unpack_from('!H', raw, pos + 2)[0]
    if total_len < ihl + 20:
        return None
    source = str(ipaddress.IPv4Address(raw[pos + 12:pos + 16]))
    target = str(ipaddress.IPv4Address(raw[pos + 16:pos + 20]))
    return _parse_tcp(raw, pos + ihl, source, target, 4)


def _ipv6(raw: bytes, pos: int) -> TcpPacket | None:
    if pos + 40 > len(raw) or raw[pos] >> 4 != 6:
        return None
    next_header = raw[pos + 6]
    cursor = pos + 40
    source = str(ipaddress.IPv6Address(raw[pos + 8:pos + 24]))
    target = str(ipaddress.IPv6Address(raw[pos + 24:pos + 40]))
    for _ in range(8):
        if next_header == 6:
            return _parse_tcp(raw, cursor, source, target, 6)
        if next_header in (0, 43, 60):  # Hop-by-Hop, Routing, Destination options
            if cursor + 2 > len(raw):
                return None
            next_protocol = raw[cursor]
            increment = (raw[cursor + 1] + 1) * 8
        elif next_header == 44:  # Fragment header
            if cursor + 8 > len(raw):
                return None
            bits = struct.unpack_from('!H', raw, cursor + 2)[0]
            if bits & 0xFFF8:
                return None
            next_protocol = raw[cursor]
            increment = 8
        elif next_header == 51:  # Authentication header
            if cursor + 2 > len(raw):
                return None
            next_protocol = raw[cursor]
            increment = (raw[cursor + 1] + 2) * 4
        else:
            return None
        if increment < 8 or cursor + increment > len(raw):
            return None
        cursor += increment
        next_header = next_protocol
    return None


def _decode_packet(raw: bytes, linktype: int) -> TcpPacket | None:
    if linktype == LINK_ETHERNET:
        if len(raw) < 14:
            return None
        ethertype = struct.unpack_from('!H', raw, 12)[0]
        pos = 14
        for _ in range(2):
            if ethertype not in (0x8100, 0x88A8, 0x9100):
                break
            if pos + 4 > len(raw):
                return None
            ethertype = struct.unpack_from('!H', raw, pos + 2)[0]
            pos += 4
        if ethertype == 0x0800:
            return _ipv4(raw, pos)
        if ethertype == 0x86DD:
            return _ipv6(raw, pos)
    elif linktype == LINK_RAW:
        if raw and raw[0] >> 4 == 4:
            return _ipv4(raw, 0)
        if raw and raw[0] >> 4 == 6:
            return _ipv6(raw, 0)
    elif linktype == LINK_IPV4:
        return _ipv4(raw, 0)
    elif linktype == LINK_IPV6:
        return _ipv6(raw, 0)
    return None


def read_pcapng(path: Path) -> tuple[list[TcpPacket], dict]:
    """Bounded pcapng reader. Supports SHB, IDB and Enhanced Packet Blocks."""
    size = path.stat().st_size
    if size > MAX_CAPTURE_BYTES:
        raise ValueError('El archivo excede 16 MiB: no se procesa una captura sin limites')
    content = path.read_bytes()
    offset = 0
    endianness = None
    interfaces: list[int] = []
    packets = []
    stats = {'bytes': size, 'blocks': 0, 'enhanced_packet_blocks': 0,
             'tcp443_packets': 0, 'unsupported_interfaces': 0,
             'truncated_packets': 0}
    while offset < len(content):
        stats['blocks'] += 1
        if stats['blocks'] > MAX_BLOCK_COUNT or len(content) - offset < 12:
            raise ValueError('Captura incompleta o excesivamente compleja')
        if content[offset:offset + 4] == b'\x0a\x0d\x0d\x0a':
            marker = content[offset + 8:offset + 12]
            if marker == b'\x4d\x3c\x2b\x1a':
                endianness = '<'
            elif marker == b'\x1a\x2b\x3c\x4d':
                endianness = '>'
            else:
                raise ValueError('Cabecera pcapng con endianness desconocido')
            interfaces = []
        elif endianness is None:
            raise ValueError('Falta cabecera de seccion pcapng')
        block_type, length = struct.unpack_from(endianness + 'II', content, offset)
        if length < 12 or length & 3 or offset + length > len(content):
            raise ValueError('Bloque pcapng truncado o longitud invalida')
        if struct.unpack_from(endianness + 'I', content, offset + length - 4)[0] != length:
            raise ValueError('Bloque pcapng con longitud final inconsistente')
        if block_type == 1:  # Interface Description Block
            if length < 20:
                raise ValueError('Descripcion de interfaz incompleta')
            linktype = struct.unpack_from(endianness + 'H', content, offset + 8)[0]
            interfaces.append(linktype)
        elif block_type == 6:  # Enhanced Packet Block
            stats['enhanced_packet_blocks'] += 1
            if length < 32:
                raise ValueError('Bloque de paquete demasiado corto')
            interface, _, _, captured, original = struct.unpack_from(
                endianness + 'IIIII', content, offset + 8
            )
            data_start = offset + 28
            data_end = data_start + captured
            if (interface >= len(interfaces) or captured > original or
                    data_end > offset + length - 4 or
                    data_start + ((captured + 3) & ~3) > offset + length - 4):
                raise ValueError('Cabecera de paquete pcapng inconsistente')
            linktype = interfaces[interface]
            if linktype not in (LINK_ETHERNET, LINK_RAW, LINK_IPV4, LINK_IPV6):
                stats['unsupported_interfaces'] += 1
            else:
                if captured < original:
                    stats['truncated_packets'] += 1
                pkt = _decode_packet(content[data_start:data_end], linktype)
                if pkt is not None:
                    packets.append(pkt)
                    stats['tcp443_packets'] += 1
                    if len(packets) > MAX_TCP_PACKET_COUNT:
                        raise ValueError('Demasiados paquetes TCP para un ensayo breve')
        offset += length
    if stats['blocks'] == 0 or not interfaces:
        raise ValueError('Archivo pcapng sin interfaces de captura')
    return packets, stats


def _external_host(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    return (ip.is_global and not ip.is_multicast and not ip.is_unspecified
            and not ip.is_loopback and not ip.is_link_local)



def _direction(packet: TcpPacket, local_addresses: set[str]) -> str:
    """Direction relative to the two exact ServerTec listener addresses."""
    if packet.destination in local_addresses and packet.destination_port == 443:
        return ('entrada_servidor_desde_ip_global' if _external_host(packet.source)
                else 'entrada_servidor_desde_ip_no_global')
    if packet.source in local_addresses and packet.source_port == 443:
        return ('respuesta_servidor_hacia_ip_global' if _external_host(packet.destination)
                else 'respuesta_servidor_hacia_ip_no_global')
    if packet.source in local_addresses and packet.destination_port == 443:
        return 'pc_como_cliente_https_saliente'
    if packet.destination in local_addresses and packet.source_port == 443:
        return 'pc_como_cliente_https_respuesta'
    return 'otros_sin_coincidencia_con_ips_listener'


def _tcp_flags(flags: int) -> str:
    if flags & RST:
        return 'rst'
    if flags & SYN and flags & ACK:
        return 'syn_ack'
    if flags & SYN:
        return 'syn'
    if flags & FIN:
        return 'fin'
    if flags & ACK:
        return 'ack_u_otros'
    return 'otros'


def summarize_directions(packets: list[TcpPacket], local_addresses: set[str]) -> dict:
    """Summarize directions and TCP flags without returning client addresses.

    Expects packets already deduplicated by analyze(). Empty IPv4/IPv6 buckets
    mean no TCP443 packets could be assigned to that IP family.
    """
    summary: dict[str, dict] = {'ipv4': {}, 'ipv6': {}}
    for packet in packets:
        family = 'ipv4' if packet.ip_version == 4 else 'ipv6'
        direction = _direction(packet, local_addresses)
        flags = _tcp_flags(packet.flags)
        entry = summary[family].setdefault(direction, {'paquetes': 0, 'flags': {}})
        entry['paquetes'] += 1
        entry['flags'][flags] = entry['flags'].get(flags, 0) + 1
    return {family: dict(sorted(buckets.items())) for family, buckets in summary.items()}


def analyze(packets: list[TcpPacket], *, v4: str = SERVER_V4,
            v6: str = SERVER_V6) -> dict:
    our_addresses = {str(ipaddress.ip_address(v4)), str(ipaddress.ip_address(v6))}
    seen = set()
    unique = []
    for pkt in packets:
        signature = (pkt.source, pkt.destination, pkt.source_port,
                     pkt.destination_port, pkt.sequence, pkt.acknowledgement, pkt.flags)
        if signature not in seen:
            seen.add(signature)
            unique.append(pkt)
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    reset_count = 0
    incoming_ack_count = 0
    for pkt in unique:
        if pkt.flags & RST:
            reset_count += 1
        if pkt.destination in our_addresses and pkt.destination_port == 443 and _external_host(pkt.source):
            key = (pkt.ip_version, pkt.source, pkt.source_port, pkt.destination, 443)
            incoming[key].append(pkt)
            if pkt.flags & ACK and not pkt.flags & SYN:
                incoming_ack_count += 1
        elif pkt.source in our_addresses and pkt.source_port == 443 and _external_host(pkt.destination):
            key = (pkt.ip_version, pkt.destination, pkt.destination_port, pkt.source, 443)
            outgoing[key].append(pkt)
    results = {'v4': {'syn': 0, 'syn_ack': 0, 'ack_complete': 0},
               'v6': {'syn': 0, 'syn_ack': 0, 'ack_complete': 0}}
    for key, seq in incoming.items():
        family = 'v4' if key[0] == 4 else 'v6'
        received_syn = [p for p in seq if p.flags & SYN and not p.flags & ACK]
        replies = [p for p in outgoing.get(key, []) if p.flags & SYN and p.flags & ACK]
        final_acks = [p for p in seq if p.flags & ACK and not p.flags & (SYN | RST)]
        for syn in received_syn:
            results[family]['syn'] += 1
            synack = next((p for p in replies
                           if p.acknowledgement == (syn.sequence + 1) & 0xFFFFFFFF), None)
            if synack is None:
                continue
            results[family]['syn_ack'] += 1
            if any(p.acknowledgement == (synack.sequence + 1) & 0xFFFFFFFF
                   and p.sequence == (syn.sequence + 1) & 0xFFFFFFFF
                   for p in final_acks):
                results[family]['ack_complete'] += 1
    ack_count = sum(part['ack_complete'] for part in results.values())
    synack_count = sum(part['syn_ack'] for part in results.values())
    syn_count = sum(part['syn'] for part in results.values())
    if ack_count:
        diagnosis = 'handshake_tcp_confirmado_en_esta_pc'
    elif synack_count:
        diagnosis = 'syn_recibido_y_synack_enviado_sin_ack_final_observado'
    elif syn_count:
        diagnosis = 'syn_recibido_sin_synack_correspondiente_observado'
    else:
        diagnosis = 'no_se_observo_syn_externo_al_destino_local'
    return {
        'status': diagnosis,
        'etapas_por_familia': results,
        'paquetes_tcp443_sin_duplicados': len(unique),
        'clasificacion_por_direccion': summarize_directions(unique, our_addresses),
        'resets_observados': reset_count,
        'acks_entrantes_sin_exigir_handshake': incoming_ack_count,
        'observaciones': [
            'Solo una captura durante el ensayo; no garantiza ausencia de paquetes perdidos.',
            'Se evitan duplicados identicos que atraviesan capas de NIC diferentes.',
            'SYN+SYN-ACK sin ACK final no acredita que la respuesta llego al visitante.',
            'Una conexion TCP completa no prueba HTTPS aceptado ni la pagina visible en Chrome.',
            'No se muestran direcciones de visitantes ni contenido capturado.',
            'Los paquetes TCP443 pueden pertenecer a conexiones HTTPS iniciadas por esta PC.',
            'Truncado en Pktmon describe captura parcial, no perdida de conectividad comprobada.',
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcapng', required=True, type=Path,
                        help='pcapng exportado por pktmon etl2pcap (archivo local privado)')
    parser.add_argument('--ipv4-local', default=SERVER_V4,
                        help='IPv4 LAN de ServerTec, verificable en Windows')
    parser.add_argument('--ipv6-local', default=SERVER_V6,
                        help='IPv6 global no temporal de ServerTec')
    args = parser.parse_args(argv)
    try:
        packets, stats = read_pcapng(args.pcapng)
        result = analyze(packets, v4=args.ipv4_local, v6=args.ipv6_local)
        result['captura'] = stats
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, struct.error) as error:
        print(f'Captura no procesada: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
