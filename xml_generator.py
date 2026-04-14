"""Generation XML Cisco SEP<MAC>.cnf.xml."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List


XML_TEMPLATE = """<device>
  <deviceProtocol>SIP</deviceProtocol>
  <devicePool>
    <dateTimeSetting>
      <dateTemplate>D/M/Y</dateTemplate>
      <timeZone>{timezone}</timeZone>
    </dateTimeSetting>
    <ntp>
      <name>{ntp}</name>
      <ntpMode>unicast</ntpMode>
    </ntp>
    <callManagerGroup>
      <members>
        <member priority="0">
          <callManager>
            <processNodeName>{uc}</processNodeName>
            <ports>
              <sipPort>5060</sipPort>
            </ports>
          </callManager>
        </member>
      </members>
    </callManagerGroup>
  </devicePool>
  <sipProfile>
    <transportLayerProtocol>1</transportLayerProtocol>
    <sipLines>
      <line button="1">
        <featureID>9</featureID>
        <featureLabel>{ext}</featureLabel>
        <proxy>USECALLMANAGER</proxy>
        <port>5060</port>
        <name>{ext}</name>
        <displayName>{ext}</displayName>
        <authName>{ext}</authName>
        <authPassword>{password}</authPassword>
      </line>
    </sipLines>
  </sipProfile>
</device>
"""


def build_xml_content(uc_server_ip: str, ntp_server_ip: str, extension: str, password: str) -> str:
    """Construit le contenu XML d'un telephone."""
    return XML_TEMPLATE.format(
        uc=uc_server_ip.strip(),
        ntp=ntp_server_ip.strip(),
        ext=extension.strip(),
        password=password.strip(),
        timezone="Central Europe Standard/Daylight Time",
    )


def build_xml_content_with_timezone(
    uc_server_ip: str,
    ntp_server_ip: str,
    extension: str,
    password: str,
    timezone: str,
) -> str:
    """Construit le XML avec timezone dynamique par telephone."""
    final_timezone = timezone.strip() or "Central Europe Standard/Daylight Time"
    return XML_TEMPLATE.format(
        uc=uc_server_ip.strip(),
        ntp=ntp_server_ip.strip(),
        ext=extension.strip(),
        password=password.strip(),
        timezone=final_timezone,
    )


def generate_xml_files(
    phones: List[Dict[str, str]],
    uc_server_ip: str,
    ntp_server_ip: str,
    output_dir: str | Path,
) -> List[Path]:
    """Genere tous les fichiers XML SEP<MAC>.cnf.xml."""
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)

    created_files: List[Path] = []
    for phone in phones:
        mac = phone["mac"].strip().upper()
        extension = phone["ext"].strip()
        password = phone["password"].strip()
        timezone = phone.get("timezone", "").strip()
        xml_content = build_xml_content_with_timezone(
            uc_server_ip, ntp_server_ip, extension, password, timezone
        )

        file_path = folder / f"SEP{mac}.cnf.xml"
        file_path.write_text(xml_content, encoding="utf-8")
        created_files.append(file_path)
    return created_files
