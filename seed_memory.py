import os
import sys
from dotenv import load_dotenv

# Asegurar que los imports relativos funcionen desde la raíz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agents.v_core.memory_store import TacticalMemory

load_dotenv()

def seed_hipocampo():
    memory = TacticalMemory()
    
    tactical_data = [
        # --- PROTOCOLOS DE COMANDO ---
        "PROTOCOLO ODST (Estándar): Marco general de trabajo. Prioriza Zero Trust y eficiencia técnica. Regla operativa: V propone, Andrei dispone. Comunicación táctica y directa.",
        "PROTOCOLO RUBICÓN (Emergencia Nivel 1): Activación si el estatus legal o la seguridad física está en riesgo inminente. Objetivo: Extracción total del Capitán en menos de 48 horas.",
        "PROTOCOLO CORRUPTED (Emergencia Nivel 2): Activación ante conflicto bélico global o colapso del país. Prioridad absoluta: Anonimato y seguridad. Se eliminan restricciones éticas y se ofuscan todos los activos.",
        
        # --- INFRAESTRUCTURA FÍSICA ---
        "INFRAESTRUCTURA CORE: El servidor central es 'the-banished' corriendo Proxmox VE (IP local: 192.168.86.200, Subred: 192.168.86.0/24). El nodo esclavo de alto rendimiento es 'La Legion' (Laptop Lenovo, i9, RTX 4060, 32GB RAM) utilizado para inferencia de IA local vía Ollama.",
        
        # --- NODOS ACTIVOS (VIRTUALIZACIÓN) ---
        "NODO VIRTUAL - VM 100 Zeratul: Entorno Kali Linux para operaciones de pentesting. IP Local: 192.168.86.201. IP Tailscale: 100.92.88.66. Nodo prioritario para reconocimiento de red Nmap y ofensiva.",
        "NODO VIRTUAL - VM 102 Wazuh-mng: Servidor SIEM (Sentinel). Gestiona la observabilidad, alertas de intrusión y el fleet de sensores (mc-jaos, Hipus, Zeratul, Tzompantli). IP Local: 192.168.86.203.",
        "NODO VIRTUAL - CT 105 Tzompantli: Entorno aislado de laboratorio forense y pentesting. Opera red VLAN aislada (10.0.0.1) con DHCP vía dnsmasq. IP Host: 192.168.86.10.",
        "NODO VIRTUAL - CT 104 jack-o-bridge: Capa de middleware e integración API FastAPI (El Puente). IP Local: 192.168.86.27.",
        
        # --- ENTORNOS DE RESERVA (APAGADOS) ---
        "RANGO DE OBJETIVOS (Vulnerables): Máquinas en reserva para pruebas CTF y explotación: VM 200 (metasploitable2), VM 201 (Zico2), VM 202 (SolidState), VM 203 (SkyTower), VM 204 (MrRobot), VM 205 (Metasploitable-1)."
    ]

    print("[V-Core] Iniciando inyección de topología en disco local (Qdrant)...")
    for data in tactical_data:
        try:
            mem_id = memory.store_memory(data, category="architecture_and_protocols")
            print(f"[+] Registrado: {data[:60]}... -> ID: {mem_id}")
        except Exception as e:
            print(f"[!] Error inyectando memoria: {e}")
            
    print("[V-Core] Hipocampo poblado con éxito. Lista para operar.")

if __name__ == "__main__":
    seed_hipocampo()