"""Fixtures de capturas sinteticas; no necesita Pktmon, Windows ni red real."""
import ipaddress
import struct

import pytest

from analizar_handshake import analyze, read_pcapng, TcpPacket, SERVER_V4, SERVER_V6


REMOTE_V4 = '198.51.100.5'  # Sintetica; manualmente permitida en analisis directo.
# Para comprobar el criterio de IP global, los fixtures usan una direccion resoluble publica.
REMOTE_GLOBAL = '8.8.8.8'
REMOTE_GLOBAL_V6 = '2606:4700:4700::1111'


def block(n, data):
    pad = b'\0' * (-len(data) % 4)
    size = 12 + len(data) + len(pad)
    return struct.pack('<II', n, size) + data + pad + struct.pack('<I', size)


def pcapng(packets, *, link_type=1):
    section = block(0x0A0D0D0A, struct.pack('<IHHq', 0x1A2B3C4D, 1, 0, -1))
    interface = block(1, struct.pack('<HHI', link_type, 0, 128))
    events = []
    for packet in packets:
        events.append(block(6, struct.pack('<IIIII', 0, 0, 0, len(packet), len(packet)) + packet))
    return section + interface + b''.join(events)


def tcp(src_port, dst_port, seq, ack, flags):
    return struct.pack('!HHIIHHHH', src_port, dst_port, seq, ack, (5 << 12) | flags, 0, 0, 0)


def ipv4(src, dst, sport, dport, seq, ack, flags):
    tcp_header = tcp(sport, dport, seq, ack, flags)
    ip_header = (b'\x45\x00' + struct.pack('!HHH', 40, 0, 0) + b'\x40\x06\0\0'
                 + ipaddress.IPv4Address(src).packed + ipaddress.IPv4Address(dst).packed)
    return b'\x00' * 12 + b'\x08\x00' + ip_header + tcp_header


def ipv6(src, dst, sport, dport, seq, ack, flags):
    tcp_header = tcp(sport, dport, seq, ack, flags)
    ip_header = (struct.pack('!I', 0x60000000) + struct.pack('!HBB', 20, 6, 64)
                 + ipaddress.IPv6Address(src).packed + ipaddress.IPv6Address(dst).packed)
    return b'\x00' * 12 + b'\x86\xdd' + ip_header + tcp_header


def handshake(src, dst, *, version=4):
    f = ipv4 if version == 4 else ipv6
    return [f(src, dst, 43210, 443, 1000, 0, 2),
            f(dst, src, 443, 43210, 5000, 1001, 18),
            f(src, dst, 43210, 443, 1001, 5001, 16)]


def test_ipv4_complete_from_pcapng(tmp_path):
    path = tmp_path / 'sample.pcapng'
    # NIC upper/lower puede duplicar el mismo paquete: no duplicar handshake.
    frames = handshake(REMOTE_GLOBAL, SERVER_V4)
    path.write_bytes(pcapng(frames + frames))
    packets, stats = read_pcapng(path)
    assert len(packets) == 6
    assert stats['enhanced_packet_blocks'] == 6
    report = analyze(packets)
    assert report['status'] == 'handshake_tcp_confirmado_en_esta_pc'
    assert report['etapas_por_familia']['v4']['ack_complete'] == 1
    assert report['paquetes_tcp443_sin_duplicados'] == 3
    assert REMOTE_GLOBAL not in str(report)


def test_ipv6_complete_from_pcapng(tmp_path):
    path = tmp_path / 'v6.pcapng'
    path.write_bytes(pcapng(handshake(REMOTE_GLOBAL_V6, SERVER_V6, version=6)))
    packets, _ = read_pcapng(path)
    assert analyze(packets)['etapas_por_familia']['v6'] == {
        'syn': 1, 'syn_ack': 1, 'ack_complete': 1,
    }


def test_synack_without_final_ack_does_not_prove_tcp_connected():
    packets = [TcpPacket(REMOTE_GLOBAL, SERVER_V4, 43210, 443, 1000, 0, 2, 4),
               TcpPacket(SERVER_V4, REMOTE_GLOBAL, 443, 43210, 5000, 1001, 18, 4)]
    assert analyze(packets)['status'] == 'syn_recibido_y_synack_enviado_sin_ack_final_observado'


def test_syn_without_synack():
    one = [TcpPacket(REMOTE_GLOBAL, SERVER_V4, 43210, 443, 1000, 0, 2, 4)]
    assert analyze(one)['status'] == 'syn_recibido_sin_synack_correspondiente_observado'


def test_wrong_ack_does_not_confirm_handshake():
    packets = [TcpPacket(REMOTE_GLOBAL, SERVER_V4, 43210, 443, 1000, 0, 2, 4),
               TcpPacket(SERVER_V4, REMOTE_GLOBAL, 443, 43210, 5000, 1001, 18, 4),
               TcpPacket(REMOTE_GLOBAL, SERVER_V4, 43210, 443, 1001, 9999, 16, 4)]
    assert analyze(packets)['etapas_por_familia']['v4']['ack_complete'] == 0


def test_empty_sample_does_not_invent_reception(tmp_path):
    path = tmp_path / 'empty.pcapng'
    path.write_bytes(pcapng([]))
    packets, stats = read_pcapng(path)
    assert stats['tcp443_packets'] == 0
    assert analyze(packets)['status'] == 'no_se_observo_syn_externo_al_destino_local'


def test_reject_invalid_and_oversized_file(tmp_path):
    bad = tmp_path / 'bad.pcapng'
    bad.write_bytes(pcapng(handshake(REMOTE_GLOBAL, SERVER_V4))[:-3])
    with pytest.raises(ValueError):
        read_pcapng(bad)
    bad.write_bytes(b'A' * (16 * 1024 * 1024 + 1))
    with pytest.raises(ValueError):
        read_pcapng(bad)


def test_do_not_count_private_source_as_an_external_visitor():
    packets = [TcpPacket('192.168.1.64', SERVER_V4, 43210, 443, 1000, 0, 2, 4)]
    assert analyze(packets)['status'] == 'no_se_observo_syn_externo_al_destino_local'


def test_ignore_unsupported_packet_links(tmp_path):
    path = tmp_path / 'unsupported.pcapng'
    path.write_bytes(pcapng([b'\0' * 80], link_type=999))
    packets, stats = read_pcapng(path)
    assert packets == []
    assert stats['unsupported_interfaces'] == 1


def test_direction_summary_distinguishes_outbound_browser_from_inbound_server():
    own = SERVER_V4
    visitor = REMOTE_GLOBAL
    packets = [
        TcpPacket(own, visitor, 50555, 443, 10, 0, 2, 4),
        TcpPacket(visitor, own, 443, 50555, 99, 11, 18, 4),
        TcpPacket(visitor, own, 41414, 443, 100, 0, 2, 4),
        TcpPacket(own, visitor, 443, 41414, 200, 101, 18, 4),
    ]
    report = analyze(packets)
    summary = report['clasificacion_por_direccion']['ipv4']
    assert report['status'] == 'syn_recibido_y_synack_enviado_sin_ack_final_observado'
    assert summary['pc_como_cliente_https_saliente']['flags']['syn'] == 1
    assert summary['pc_como_cliente_https_respuesta']['flags']['syn_ack'] == 1
    assert summary['entrada_servidor_desde_ip_global']['flags']['syn'] == 1
    assert summary['respuesta_servidor_hacia_ip_global']['flags']['syn_ack'] == 1
    assert sum(group['paquetes'] for group in summary.values()) == 4
    assert visitor not in str(report)


def test_all_outbound_does_not_claim_external_syn_arrived():
    packets = [
        TcpPacket(SERVER_V4, REMOTE_GLOBAL, 50444, 443, 100, 0, 2, 4),
        TcpPacket(REMOTE_GLOBAL, SERVER_V4, 443, 50444, 300, 101, 18, 4),
    ]
    report = analyze(packets)
    assert report['status'] == 'no_se_observo_syn_externo_al_destino_local'
    groups = report['clasificacion_por_direccion']['ipv4']
    assert groups['pc_como_cliente_https_saliente']['paquetes'] == 1
    assert groups['pc_como_cliente_https_respuesta']['paquetes'] == 1
    assert 'entrada_servidor_desde_ip_global' not in groups


def test_lan_client_does_not_masquerade_as_external_visitor():
    packets = [
        TcpPacket('192.168.1.64', SERVER_V4, 40123, 443, 100, 0, 2, 4),
        TcpPacket(SERVER_V4, '192.168.1.64', 443, 40123, 300, 101, 18, 4),
    ]
    r = analyze(packets)
    groups = r['clasificacion_por_direccion']['ipv4']
    assert r['status'] == 'no_se_observo_syn_externo_al_destino_local'
    assert groups['entrada_servidor_desde_ip_no_global']['flags']['syn'] == 1
    assert groups['respuesta_servidor_hacia_ip_no_global']['flags']['syn_ack'] == 1


def test_ipv6_public_traffic_and_duplicates_are_counted_once():
    packets = [
        TcpPacket(REMOTE_GLOBAL_V6, SERVER_V6, 40123, 443, 100, 0, 2, 6),
        TcpPacket(SERVER_V6, REMOTE_GLOBAL_V6, 443, 40123, 300, 101, 18, 6),
        TcpPacket(REMOTE_GLOBAL_V6, SERVER_V6, 40123, 443, 100, 0, 2, 6),
    ]
    r = analyze(packets)
    assert r['paquetes_tcp443_sin_duplicados'] == 2
    assert r['clasificacion_por_direccion']['ipv4'] == {}
    groups = r['clasificacion_por_direccion']['ipv6']
    assert groups['entrada_servidor_desde_ip_global']['paquetes'] == 1
    assert groups['respuesta_servidor_hacia_ip_global']['paquetes'] == 1
    assert REMOTE_GLOBAL_V6 not in str(r)


def test_unknown_local_ip_or_other_listener_is_not_attributed_to_servertec():
    packets = [TcpPacket('8.8.4.4', '192.168.1.99', 51000, 443, 100, 0, 2, 4)]
    r = analyze(packets)
    assert r['status'] == 'no_se_observo_syn_externo_al_destino_local'
    assert r['clasificacion_por_direccion']['ipv4']['otros_sin_coincidencia_con_ips_listener']['paquetes'] == 1
    assert '8.8.4.4' not in str(r)
