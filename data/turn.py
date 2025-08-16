import pandas as pd
import json
import os
from datetime import datetime

xlsx_path = "CLASSES ULTRAS - ULTRAHUB.xlsx"
output_dir = "output_comps/"
os.makedirs(output_dir, exist_ok=True)

# Carregar todas as abas sem cabeçalho
xls = pd.read_excel(xlsx_path, sheet_name=None, header=None)

# Carregar aba de builds
builds_df = pd.read_excel(xlsx_path, sheet_name="BUILDS", header=0)
builds_df.columns = [str(col).strip().lower() for col in builds_df.columns]

# Classes válidas (da aba MOON e BUILDS)
valid_classes = {
    'LORD OF ORDER', 'LEGION REVENANT', 'ARCHPALADIN', 'VERUS DOOMKNIGHT',
    'OBSIDIAN PALADIN CHRONOMANCER', 'CHAOS AVENGER', 'CHRONO SHADOWHUNTER',
    'QUANTUM CHRONOMANCER', 'STONECRUSHER', 'DRAGON OF TIME', 'VOID HIGHLORD',
    'SHAMAN', 'ARCANA INVOKER', 'SENTINEL', 'ARCHFIEND', 'NECROTIC CHRONOMANCER',
    'LIGHTCASTER', 'GLACERAN WARLORD'
}

def format_title_case(s):
    """Formata strings para Title Case corretamente"""
    if not s:
        return s
    return ' '.join(
        word.capitalize() if word.upper() not in ['OF', 'THE'] else word.lower()
        for word in s.split()
    )

def get_enhancements(class_name):
    """Busca e formata enhancements na aba BUILDS"""
    class_row = builds_df[builds_df['class'].str.strip().str.upper() == class_name.upper()]
    if not class_row.empty:
        return {
            'weapon': format_title_case(class_row.iloc[0]['weapon']),
            'helm': format_title_case(class_row.iloc[0]['helm']),
            'cape': format_title_case(class_row.iloc[0]['cape']),
            'armor': format_title_case(class_row.iloc[0].get('armor', ''))
        }
    return {}

def process_sheet(df):
    """Processa cada aba detectando blocos de 5 linhas"""
    compositions = []
    current_block = []
    comp_counter = {}
    
    for _, row in df.iterrows():
        cell_value = str(row[0]).strip()
        
        # Ignorar linhas totalmente vazias apenas se forem delimitadores
        if cell_value == 'nan':
            if len(current_block) >= 5:
                # Processar bloco com título + 4 classes
                title = format_title_case(current_block[0])
                classes = [format_title_case(c) for c in current_block[1:5] if c in valid_classes]
                
                if classes:
                    base_name = title if title else "Unnamed"
                    if base_name in comp_counter:
                        comp_counter[base_name] += 1
                        comp_name = f"{base_name} {comp_counter[base_name]}"
                    else:
                        comp_counter[base_name] = 0
                        comp_name = base_name
                    
                    compositions.append({
                        'name': comp_name,
                        'classes': classes
                    })
                current_block = []
            continue
            
        current_block.append(cell_value)
        
    # Processar último bloco se houver
    if len(current_block) >= 5:
        title = format_title_case(current_block[0])
        classes = [format_title_case(c) for c in current_block[1:5] if c in valid_classes]
        if classes:
            base_name = title if title else "Unnamed"
            comp_name = f"{base_name} {comp_counter[base_name]}" if base_name in comp_counter else base_name
            compositions.append({
                'name': comp_name,
                'classes': classes
            })
    
    return compositions

for sheet_name, df in xls.items():
    if sheet_name == "BUILDS": continue
    
    print(f"Processando {sheet_name}...")
    comps = process_sheet(df)
    
    # Gerar JSON
    output = []
    for comp in comps:
        setup = {}
        for cls in comp['classes']:
            enh = get_enhancements(cls.upper())  # Busca pelo nome original em maiúsculas
            if enh:
                setup[cls] = {
                    'items': [],
                    'enhancements': enh
                }
        
        output.append({
            'name': comp['name'],
            'classes': comp['classes'],
            'recommended_setup': setup,
            'author': 'Jix',
            'dtCreated': datetime.now().timestamp(),
            'dtUpdated': datetime.now().timestamp(),
            'difficulty': 'Unknown',
            'strategy': '',
            'video_url': '',
            'thumbnail_url': ''
        })
    
    # Salvar arquivo
    filename = f"{sheet_name.replace(' ', '_')}.json"
    output_path = os.path.join(output_dir, filename)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)
    
    print(f"✅ {filename} gerado com {len(output)} composições")

print("\n✅ Conversão concluída!")