<?xml version="1.0" encoding="UTF-8"?>
<!--
  Sample IEC 61850 SCD File
  Substation: Meadowbrook 115kV Bay 1
  IEDs:
    PROT1  — Line protection relay (publisher: PTOC, PDIF, XCBR status)
    PROT2  — Bus protection relay (publisher: PDIF busbar)
    RTAC1  — SEL RTAC (subscriber)
-->
<SCL xmlns="http://www.iec.ch/61850/2003/SCL"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     version="2007" revision="B" release="4">

  <Header id="Meadowbrook_Bay1" version="1" revision="2"
          toolID="IEC61850-MCP-Sample" nameStructure="IEDName"/>

  <!-- ============================================================ -->
  <!-- Communication Section                                        -->
  <!-- ============================================================ -->
  <Communication>
    <SubNetwork name="ProcessBus" type="8-MMS">
      <BitRate unit="b/s" multiplier="M">100</BitRate>

      <!-- PROT1 access point -->
      <ConnectedAP iedName="PROT1" apName="S1">
        <Address>
          <P type="IP">192.168.1.101</P>
          <P type="IP-SUBNET">255.255.255.0</P>
          <P type="IP-GATEWAY">192.168.1.1</P>
        </Address>
        <!-- GOOSE: Line protection trip -->
        <GSE ldInst="LD0" cbName="GCB_PROT">
          <Address>
            <P type="MAC-Address">01:0C:CD:01:00:01</P>
            <P type="APPID">0001</P>
            <P type="VLAN-ID">000</P>
            <P type="VLAN-PRIORITY">4</P>
          </Address>
          <MinTime unit="ms">4</MinTime>
          <MaxTime unit="ms">1000</MaxTime>
        </GSE>
        <!-- GOOSE: CB position feedback -->
        <GSE ldInst="LD0" cbName="GCB_STATUS">
          <Address>
            <P type="MAC-Address">01:0C:CD:01:00:02</P>
            <P type="APPID">0002</P>
            <P type="VLAN-ID">000</P>
            <P type="VLAN-PRIORITY">4</P>
          </Address>
          <MinTime unit="ms">4</MinTime>
          <MaxTime unit="ms">5000</MaxTime>
        </GSE>
      </ConnectedAP>

      <!-- PROT2 access point -->
      <ConnectedAP iedName="PROT2" apName="S1">
        <Address>
          <P type="IP">192.168.1.102</P>
          <P type="IP-SUBNET">255.255.255.0</P>
          <P type="IP-GATEWAY">192.168.1.1</P>
        </Address>
        <GSE ldInst="LD0" cbName="GCB_BUS">
          <Address>
            <P type="MAC-Address">01:0C:CD:01:00:10</P>
            <P type="APPID">0010</P>
            <P type="VLAN-ID">000</P>
            <P type="VLAN-PRIORITY">4</P>
          </Address>
          <MinTime unit="ms">4</MinTime>
          <MaxTime unit="ms">1000</MaxTime>
        </GSE>
      </ConnectedAP>

      <!-- RTAC1 access point -->
      <ConnectedAP iedName="RTAC1" apName="S1">
        <Address>
          <P type="IP">192.168.1.200</P>
          <P type="IP-SUBNET">255.255.255.0</P>
          <P type="IP-GATEWAY">192.168.1.1</P>
        </Address>
      </ConnectedAP>

    </SubNetwork>
  </Communication>

  <!-- ============================================================ -->
  <!-- IED: PROT1 — Line Protection Relay                          -->
  <!-- ============================================================ -->
  <IED name="PROT1" desc="Line Protection Relay - Bay 1" type="SEL-411L"
       manufacturer="SEL" configVersion="1">
    <AccessPoint name="S1">
      <Server>
        <LDevice inst="LD0" desc="Line Protection">

          <LN0 lnClass="LLN0" inst="" lnType="LLN0_Type">
            <!-- Dataset 1: Protection trip signals -->
            <DataSet name="DS_PROT" desc="Protection Trip Signals">
              <FCDA ldInst="LD0" prefix="" lnClass="PTOC" lnInst="1"
                    doName="Op" daName="general" fc="ST"/>
              <FCDA ldInst="LD0" prefix="" lnClass="PTOC" lnInst="1"
                    doName="Op" daName="q" fc="ST"/>
              <FCDA ldInst="LD0" prefix="" lnClass="PDIF" lnInst="1"
                    doName="Op" daName="general" fc="ST"/>
              <FCDA ldInst="LD0" prefix="" lnClass="PDIF" lnInst="1"
                    doName="Op" daName="q" fc="ST"/>
              <FCDA ldInst="LD0" prefix="" lnClass="PTOC" lnInst="2"
                    doName="Str" daName="general" fc="ST"/>
            </DataSet>

            <!-- Dataset 2: CB position and status -->
            <DataSet name="DS_STATUS" desc="CB Position and Status">
              <FCDA ldInst="LD0" prefix="" lnClass="XCBR" lnInst="1"
                    doName="Pos" daName="stVal" fc="ST"/>
              <FCDA ldInst="LD0" prefix="" lnClass="XCBR" lnInst="1"
                    doName="Pos" daName="q" fc="ST"/>
              <FCDA ldInst="LD0" prefix="" lnClass="XSWI" lnInst="1"
                    doName="Pos" daName="stVal" fc="ST"/>
              <FCDA ldInst="LD0" prefix="" lnClass="RREC" lnInst="1"
                    doName="Op" daName="general" fc="ST"/>
            </DataSet>

            <!-- GOOSE Control Block 1: Protection trips -->
            <GSEControl name="GCB_PROT" desc="Line Protection Trip GOOSE"
                        type="GOOSE" datSet="DS_PROT" confRev="3"
                        fixedOffs="false">
            </GSEControl>

            <!-- GOOSE Control Block 2: Status -->
            <GSEControl name="GCB_STATUS" desc="CB Position Status GOOSE"
                        type="GOOSE" datSet="DS_STATUS" confRev="2"
                        fixedOffs="false">
            </GSEControl>
          </LN0>

          <!-- Logical Nodes -->
          <LN lnClass="PTOC" inst="1" lnType="PTOC_Type" prefix=""
              desc="Overcurrent Protection Zone 1"/>
          <LN lnClass="PTOC" inst="2" lnType="PTOC_Type" prefix=""
              desc="Overcurrent Protection Zone 2"/>
          <LN lnClass="PDIF" inst="1" lnType="PDIF_Type" prefix=""
              desc="Line Differential Protection"/>
          <LN lnClass="XCBR" inst="1" lnType="XCBR_Type" prefix=""
              desc="Circuit Breaker CB1"/>
          <LN lnClass="XSWI" inst="1" lnType="XSWI_Type" prefix=""
              desc="Disconnector DS1"/>
          <LN lnClass="RREC" inst="1" lnType="RREC_Type" prefix=""
              desc="Autorecloser"/>

        </LDevice>
      </Server>
    </AccessPoint>
  </IED>

  <!-- ============================================================ -->
  <!-- IED: PROT2 — Bus Protection Relay                           -->
  <!-- ============================================================ -->
  <IED name="PROT2" desc="Busbar Protection Relay" type="SEL-487B"
       manufacturer="SEL" configVersion="1">
    <AccessPoint name="S1">
      <Server>
        <LDevice inst="LD0" desc="Bus Protection">

          <LN0 lnClass="LLN0" inst="" lnType="LLN0_Type">
            <DataSet name="DS_BUS" desc="Busbar Protection Trip Signals">
              <FCDA ldInst="LD0" prefix="" lnClass="PDIF" lnInst="1"
                    doName="Op" daName="general" fc="ST"/>
              <FCDA ldInst="LD0" prefix="" lnClass="PDIF" lnInst="1"
                    doName="Op" daName="q" fc="ST"/>
              <FCDA ldInst="LD0" prefix="" lnClass="PTOC" lnInst="1"
                    doName="Op" daName="general" fc="ST"/>
            </DataSet>

            <GSEControl name="GCB_BUS" desc="Busbar Protection Trip GOOSE"
                        type="GOOSE" datSet="DS_BUS" confRev="1"
                        fixedOffs="false">
            </GSEControl>
          </LN0>

          <LN lnClass="PDIF" inst="1" lnType="PDIF_Type" prefix=""
              desc="Busbar Differential Protection"/>
          <LN lnClass="PTOC" inst="1" lnType="PTOC_Type" prefix=""
              desc="Bus Backup Overcurrent"/>

        </LDevice>
      </Server>
    </AccessPoint>
  </IED>

  <!-- ============================================================ -->
  <!-- IED: RTAC1 — SEL RTAC Subscriber                           -->
  <!-- ============================================================ -->
  <IED name="RTAC1" desc="SEL RTAC Bay 1 Controller" type="SEL-3555"
       manufacturer="SEL" configVersion="1">
    <AccessPoint name="S1">
      <Server>
        <LDevice inst="LD0" desc="RTAC Main">
          <LN0 lnClass="LLN0" inst="" lnType="LLN0_Type">
            <Inputs>
              <!-- Subscribe to PROT1 trip signals -->
              <ExtRef iedName="PROT1" ldInst="LD0" lnClass="PTOC" lnInst="1"
                      doName="Op" daName="general" fc="ST"
                      desc="Line OC Trip Z1"/>
              <ExtRef iedName="PROT1" ldInst="LD0" lnClass="PDIF" lnInst="1"
                      doName="Op" daName="general" fc="ST"
                      desc="Line Diff Trip"/>
              <!-- Subscribe to PROT2 bus trip -->
              <ExtRef iedName="PROT2" ldInst="LD0" lnClass="PDIF" lnInst="1"
                      doName="Op" daName="general" fc="ST"
                      desc="Bus Diff Trip"/>
            </Inputs>
          </LN0>
        </LDevice>
      </Server>
    </AccessPoint>
  </IED>

</SCL>
