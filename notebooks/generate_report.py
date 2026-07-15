#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import json
import os
from datetime import datetime
from xml.sax.saxutils import escape

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, HRFlowable
from reportlab.lib.units import cm


def generate_report(zone, output_path=None, before_path=None, after_path=None):
    if output_path is None:
        output_path = os.path.join(BASE_DIR, f"data/report_zone_{zone['id']}.pdf")
    if before_path is None:
        before_path = os.path.join(BASE_DIR, f"data/images/zone_{zone['id']}_before.png")
    if after_path is None:
        after_path = os.path.join(BASE_DIR, f"data/images/zone_{zone['id']}_after.png")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []

    severity_hex = {
        'CRITICAL': '#CC0000',
        'HIGH': '#FF6600',
        'MEDIUM': '#CCAA00',
        'LOW': '#006600',
    }

    sev = zone.get('severity', 'LOW')
    score = zone.get('risk_score', 0)
    area = zone.get('area_sqm', 0)
    violation = zone.get('violation_type', 'UNVERIFIED_ZONE')
    bhuvan_land_type = zone.get('bhuvan_land_type') or 'Not assessed'
    bhuvan_confidence = zone.get('bhuvan_confidence') or 'Unknown'
    bhuvan_overlap = float(zone.get('bhuvan_overlap_percent') or 0)
    bhuvan_source = zone.get('bhuvan_source') or 'No land-use layer available for this zone'
    area_label = zone.get('area_label', 'Selected area')
    period_label = zone.get('period_label', '2019-2023')
    if ' vs ' in period_label:
        before_year, after_year = period_label.split(' vs ')
    else:
        before_year, after_year = '2019', '2023'

    title_style = ParagraphStyle('title', fontSize=22, fontName='Helvetica-Bold',
        textColor=colors.HexColor('#CC0000'), spaceAfter=4)
    story.append(Paragraph('AutoSentinel', title_style))

    sub_style = ParagraphStyle('sub', fontSize=11, fontName='Helvetica',
        textColor=colors.HexColor('#444444'), spaceAfter=2)
    story.append(Paragraph('Unauthorized Construction Detection Report', sub_style))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M IST')}  |  "
        f'Area: {area_label}  |  Analysis Period: {before_year}-{after_year}',
        ParagraphStyle('meta', fontSize=8, textColor=colors.HexColor('#888888'))))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#DDDDDD'), spaceAfter=12))

    sev_style = ParagraphStyle('sev', fontSize=16, fontName='Helvetica-Bold',
        textColor=colors.HexColor(severity_hex.get(sev, '#006600')), spaceAfter=4)
    story.append(Paragraph(f'Severity: {sev}  |  Risk Score: {score}/100', sev_style))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph('Zone Details', ParagraphStyle('h2', fontSize=13,
        fontName='Helvetica-Bold', spaceAfter=6, textColor=colors.HexColor('#222222'))))

    details_data = [
        ['Field', 'Value'],
        ['Zone ID', str(zone.get('id', 'unknown'))],
        ['Coordinates', f"{zone.get('lat', 0):.6f}°N, {zone.get('lon', 0):.6f}°E"],
        ['Constructed Area', f"{area / 10000:.2f} hectares  ({area:,.0f} sq metres)"],
        ['Severity Level', sev],
        ['Risk Score', f"{score} / 100"],
        ['Violation Type', violation.replace('_', ' ')],
        ['Bhuvan Land Classification', str(bhuvan_land_type)],
        ['Bhuvan Overlap / Confidence', f"{bhuvan_overlap:.1f}% / {bhuvan_confidence}"],
        ['Bhuvan Data Source', str(bhuvan_source)],
        ['OSM Overlays', ', '.join(zone.get('osm_flags', [])) or 'None'],
        ['Legal Flags', ', '.join(zone.get('legal_flags', [])) or 'None'],
        ['Risk Boost', f"{zone.get('risk_boost_total', 0):.1f}"],
    ]

    table = Table(details_data, colWidths=[6 * cm, 11 * cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#222222')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F9F9F9'), colors.white]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph('Bhuvan Land-use Verification', ParagraphStyle('h2_bhuvan', fontSize=13,
        fontName='Helvetica-Bold', spaceAfter=6, textColor=colors.HexColor('#222222'))))
    story.append(Paragraph(
        f"The zone was checked against the available ISRO Bhuvan-compatible land-use layer. "
        f"Dominant classification: <b>{escape(str(bhuvan_land_type))}</b>; polygon overlap: <b>{bhuvan_overlap:.1f}%</b>; "
        f"confidence: <b>{escape(str(bhuvan_confidence))}</b>. Source: {escape(str(bhuvan_source))}.",
        ParagraphStyle('bhuvan_note', fontSize=9, textColor=colors.HexColor('#555555'),
            leading=14, spaceAfter=10)))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#DDDDDD'), spaceAfter=8))
    story.append(Paragraph('How the Risk Score Was Calculated',
        ParagraphStyle('h2', fontSize=13, fontName='Helvetica-Bold',
            spaceAfter=6, textColor=colors.HexColor('#222222'))))

    if area > 50000:
        score_reason = (
            f"This zone received a CRITICAL score of {score}/100 because the detected construction "
            f"covers {area / 10000:.1f} hectares - exceeding the 5-hectare threshold that indicates "
            'large-scale unauthorized development. Structures of this size cannot be accidental '
            'extensions and should be reviewed against local approvals.'
        )
    elif area > 10000:
        score_reason = (
            f"This zone received a HIGH score of {score}/100 because the detected construction "
            f"covers {area / 10000:.1f} hectares - between 1 and 5 hectares. This scale of development "
            'on unverified land indicates significant unauthorized construction activity.'
        )
    elif area > 2000:
        score_reason = (
            f"This zone received a MEDIUM score of {score}/100 because the detected construction "
            f"covers {area / 10000:.2f} hectares - between 0.2 and 1 hectare. This is a moderate "
            'satellite-detected change requiring human verification.'
        )
    else:
        score_reason = (
            f"This zone received a LOW score of {score}/100 because the detected construction "
            f"covers {area:.0f} sq metres - a small satellite-detected built-up change."
        )

    violation_reason = {
        'FOREST_ENCROACHMENT': (
            'The construction location falls within an area classified as protected forest or woodland '
            'in the available reference overlays. Construction on forest land without Forest Department '
            'clearance may be prohibited under the Forest Conservation Act, 1980.'
        ),
        'AGRICULTURAL_LAND': (
            'The construction location falls on land classified as agricultural. Converting agricultural '
            'land to non-agricultural use without Maharashtra government permission violates the '
            'Maharashtra Land Revenue Code.'
        ),
        'WATER_BODY_ENCROACHMENT': (
            'The construction is detected near or within a water body buffer zone. Construction in '
            'these areas is prohibited under CRZ and water body protection regulations.'
        ),
        'UNVERIFIED_ZONE': (
            'The land classification for this zone could not be verified against available zoning data. '
            'The flag is based solely on the magnitude of satellite-detected construction change. '
            'Ground verification is required to determine the applicable land use rules.'
        ),
    }.get(violation, 'Land classification pending verification.')

    score_breakdown_data = [
        ['Scoring Factor', 'Value', 'Contribution'],
        ['Construction Area', f"{area / 10000:.2f} ha", 'Primary driver - larger = higher score'],
        ['Land Classification', violation.replace('_', ' '), 'Determines violation severity'],
        ['NDBI Change Magnitude', '> 0.15 threshold', 'Confirms built-up area increase'],
        ['Time Period', f'{before_year} → {after_year}', 'Change detection window'],
        ['Final Score', f"{score}/100", f"Severity: {sev}"],
    ]

    breakdown_table = Table(score_breakdown_data, colWidths=[5 * cm, 5 * cm, 7 * cm])
    breakdown_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F5F5F5'), colors.white]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ('PADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(breakdown_table)
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph(score_reason,
        ParagraphStyle('body', fontSize=9, textColor=colors.HexColor('#333333'),
            leading=14, spaceAfter=8)))
    story.append(Paragraph(f'Land Classification Note: {violation_reason}',
        ParagraphStyle('body2', fontSize=9, textColor=colors.HexColor('#555555'),
            leading=14, spaceAfter=8)))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#DDDDDD'), spaceAfter=8))
    story.append(Paragraph('Satellite Evidence',
        ParagraphStyle('h2', fontSize=13, fontName='Helvetica-Bold',
            spaceAfter=6, textColor=colors.HexColor('#222222'))))

    if os.path.exists(before_path) and os.path.exists(after_path):
        story.append(Paragraph(
            f'The images below show the flagged location in {before_year} (before) and {after_year} (after). '
            'Visible change in land cover - new grey/brown built-up area replacing green or open land - '
            'confirms the satellite detection.',
            ParagraphStyle('body', fontSize=9, textColor=colors.HexColor('#555555'),
                leading=14, spaceAfter=8)))

        img_before = RLImage(before_path, width=8 * cm, height=8 * cm)
        img_after = RLImage(after_path, width=8 * cm, height=8 * cm)
        label_style = ParagraphStyle('label', fontSize=8, alignment=1,
            textColor=colors.HexColor('#666666'))

        img_table = Table(
            [[img_before, img_after],
             [Paragraph(f'{before_year} - Before Construction', label_style),
              Paragraph(f'{after_year} - After Construction', label_style)]],
            colWidths=[8.5 * cm, 8.5 * cm]
        )
        img_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('PADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(img_table)
    else:
        story.append(Paragraph(
            'Satellite image crops are not available for this zone. '
            'Images are pre-generated for Critical severity zones only. '
            'Use the AutoSentinel dashboard to view live satellite thumbnails for this location.',
            ParagraphStyle('body', fontSize=9, textColor=colors.HexColor('#888888'), leading=14)))

    story.append(Spacer(1, 0.5 * cm))

    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#DDDDDD'), spaceAfter=6))
    story.append(Paragraph(
        'DISCLAIMER: This report is auto-generated by AutoSentinel using satellite remote sensing '
        'and should be treated as a preliminary flag for human review. Satellite detection is based '
        'on NDBI change analysis of Sentinel-2 imagery (10m resolution) and may include false positives '
        'due to legitimate permitted construction not reflected in available zoning data. '
        'Final enforcement decisions must be made by authorized municipal officers following '
        'ground verification.',
        ParagraphStyle('disclaimer', fontSize=7, textColor=colors.HexColor('#999999'), leading=11)))

    doc.build(story)
    print(f'Report saved: {output_path}')


if __name__ == '__main__':
    with open(os.path.join(BASE_DIR, 'data/flagged_zones.json'), encoding='utf-8') as f:
        zones = json.load(f)

    zone_id = sys.argv[1] if len(sys.argv) > 1 else str(zones[0]['id'])
    zone = next((z for z in zones if str(z['id']) == str(zone_id)), zones[0])
    generate_report(zone)
