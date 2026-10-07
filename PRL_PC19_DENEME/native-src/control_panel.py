"""Independent Windows desktop controller. --demo never opens an agent server."""
import argparse
import json
import math
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk, font as tkfont

from panel_server import PanelStore, serve
from signals import read_json
from runtime_paths import application_root

ROOT = application_root(__file__)


def safe_number(value, digits=1):
    return f'{value:.{digits}f}' if type(value) in (int, float) and math.isfinite(value) else '—'


def row_values(pc, snapshot, now):
    heartbeat = snapshot['heartbeat']
    online = heartbeat is not None and now - heartbeat['received_at'] <= 10
    data = heartbeat['data'] if online else {}
    vision = data.get('vision', {})
    if not isinstance(vision, dict):
        vision = {}
    image = ('BOŞ / DOĞRULANDI' if vision.get('usable') is True else 'MÜŞTERİ EKRANI'
        if vision.get('session_occupied') is True else 'EŞLEŞTİ / DENEME' if vision.get('matched') is True else 'BELİRSİZ')
    gpus = data.get('gpus', [])
    temperature = gpus[0].get('temperature_c') if isinstance(gpus, list) and gpus and isinstance(gpus[0], dict) else None
    profits = data.get('estimated_profit_try_per_hour', {})
    profit = profits.get('pearl') if isinstance(profits, dict) else None
    state = 'ÇALIŞIYOR' if data.get('mining') is True else 'BEKLİYOR' if online else '—'
    desired = 'OTOMATİK' if snapshot['command']['desired_state'] == 'auto' else 'DURAKLAT'
    reason = str(data.get('reason', 'Ajan bağlantısı bekleniyor'))[:150]
    return (pc, 'BAĞLI' if online else 'ÇEVRİMDIŞI', desired, image, state,
            str(data.get('oc_state', '—')), safe_number(temperature), safe_number(profit, 2),
            safe_number(data.get('wait_remaining_seconds'), 0), reason)


class Panel:
    def __init__(self, root, store, demo=False, server=None):
        self.root, self.store, self.demo, self.server = root, store, demo, server
        self.search = tk.StringVar()
        self.notice = tk.StringVar(value='Genel durdurma açık. Önce bağlantıları ve görsel doğrulamayı kontrol et.')
        root.title('Kampüs Game Arena • PRL Kontrol' + (' • DEMO' if demo else ''))
        root.geometry('1500x860'); root.minsize(1000, 650); root.configure(bg='#10151e')
        ui_font = 'Segoe UI' if 'Segoe UI' in tkfont.families(root) else 'Helvetica'
        style = ttk.Style(root); style.theme_use('clam')
        style.configure('Treeview', background='#151c28', foreground='#e6edf5',
                        fieldbackground='#151c28', rowheight=33, borderwidth=0, font=(ui_font, 10))
        style.configure('Treeview.Heading', background='#263248', foreground='#e6edf5', font=(ui_font, 10, 'bold'))
        style.map('Treeview', background=[('selected', '#354766')])
        header = tk.Frame(root, bg='#10151e'); header.pack(fill='x', padx=25, pady=(22, 10))
        tk.Label(header, text='KAMPÜS  /  PRL KONTROL', bg='#10151e', fg='#f1f5fb',
                 font=(ui_font, 22, 'bold')).pack(anchor='w')
        subtitle = 'DEMO — Örnek durumlar; gerçek cihaz veya mining bağlantısı yok.' if demo else 'Bağımsız kasa paneli • Her cihaz kendi kilit resmini kontrol eder'
        tk.Label(header, text=subtitle, bg='#10151e', fg='#9eacc3', font=(ui_font, 11)).pack(anchor='w', pady=(7, 0))
        self.summary = tk.StringVar()
        tk.Label(root, textvariable=self.summary, bg='#202b3e', fg='#e6edf5',
                 font=(ui_font, 13, 'bold'), padx=20, pady=18).pack(fill='x', padx=25, pady=12)
        toolbar = tk.Frame(root, bg='#10151e'); toolbar.pack(fill='x', padx=25, pady=(0, 12))
        buttons = [('Seçileni otomatik', 'auto', '#244c42'), ('Seçileni durdur', 'paused', '#293950'),
                   ('OC normale dön', 'stock', '#293950'), ('Hata kilidini kaldır', 'clear_fault', '#694c20'),
                   ('Tümünü otomatik', 'all_auto', '#244c42'),
                   ('Genel durdurmayı kaldır', 'release', '#694c20'), ('HEPSİNİ DURDUR', 'emergency', '#a42c3a')]
        for i, (label, action, color) in enumerate(buttons):
            tk.Button(toolbar, text=label, command=lambda a=action: self.command(a),
                bg=color, fg='white', activebackground=color, activeforeground='white',
                font=(ui_font, 10, 'bold'), relief='flat', padx=12, pady=10).grid(row=i//4, column=i%4, sticky='ew', padx=(0, 7), pady=(0, 7))
        for column in range(4):
            toolbar.grid_columnconfigure(column, weight=1)
        filterbar = tk.Frame(root, bg='#10151e'); filterbar.pack(fill='x', padx=25, pady=(0, 10))
        tk.Label(filterbar, text='Bilgisayar ara', bg='#10151e', fg='#9eacc3', font=(ui_font, 10)).pack(side='left', padx=(0, 12))
        entry = tk.Entry(filterbar, textvariable=self.search, bg='#202b3e', fg='white',
                         insertbackground='white', relief='flat', font=(ui_font, 12))
        entry.pack(side='left', fill='x', expand=True)
        tableframe = tk.Frame(root, bg='#10151e'); tableframe.pack(fill='both', expand=True, padx=25)
        columns = ('pc', 'connection', 'desired', 'image', 'mining', 'oc', 'temp', 'profit', 'wait', 'reason')
        self.table = ttk.Treeview(tableframe, columns=columns, show='headings', selectmode='extended')
        titles = ['Bilgisayar', 'Bağlantı', 'Kontrol', 'Kilit resmi', 'Mining', 'OC', 'GPU °C', 'TL/saat · tahmin', 'Kalan sn', 'Durum / neden']
        widths = [160, 105, 100, 155, 115, 115, 70, 125, 75, 290]
        for key, title, width in zip(columns, titles, widths):
            self.table.heading(key, text=title); self.table.column(key, width=width, minwidth=60, stretch=key=='reason')
        vertical = ttk.Scrollbar(tableframe, orient='vertical', command=self.table.yview)
        horizontal = ttk.Scrollbar(tableframe, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.grid(row=0, column=0, sticky='nsew'); vertical.grid(row=0, column=1, sticky='ns'); horizontal.grid(row=1, column=0, sticky='ew')
        tableframe.grid_rowconfigure(0, weight=1); tableframe.grid_columnconfigure(0, weight=1)
        self.table.tag_configure('offline', foreground='#7f8ca2')
        self.table.tag_configure('mining', foreground='#65d9a7')
        self.table.bind('<Double-1>', self.details)
        tk.Label(root, textvariable=self.notice, bg='#10151e', fg='#efbf77',
                 font=(ui_font, 10), anchor='w', wraplength=1400).pack(fill='x', padx=25, pady=18)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def command(self, action):
        pcs = list(self.table.selection())
        if action == 'all_auto':
            pcs = list(self.store.devices); action = 'auto'
        if action not in ('release', 'emergency') and not pcs:
            self.notice.set('Önce bir veya birden fazla bilgisayar seç.'); return
        try:
            self.store.command(pcs, action)
        except Exception as exc:
            self.store.emergency_stop = True
            self.notice.set(f'Merkezi kayıt hatası; işlem durduruldu: {exc}')
            return
        self.notice.set('Komut ' + ('DEMO durumuna uygulandı.' if self.demo else
            'kaydedildi; bağlı ajanlar sonraki durum alışverişinde alır. Görsel/giriş/ısı kontrolleri geçerlidir.'))
        self.refresh(schedule=False)

    def details(self, _event=None):
        selected = self.table.selection()
        if not selected:
            return
        pc = selected[0]
        window = tk.Toplevel(self.root); window.title(pc + ' • Ayrıntı'); window.geometry('850x650')
        text = tk.Text(window, bg='#151c28', fg='#e6edf5', font=('Consolas', 11), wrap='word')
        text.pack(fill='both', expand=True)
        text.insert('1.0', json.dumps(self.store.snapshot()[pc], ensure_ascii=False, indent=2))
        text.configure(state='disabled')

    def refresh(self, schedule=True):
        now = time.time()
        if self.demo:
            self.fill_demo(now)
        snapshot = self.store.snapshot(); needle = self.search.get().strip().upper()
        visible = {pc for pc in snapshot if needle in pc}
        for pc in self.table.get_children():
            if pc not in visible:
                self.table.delete(pc)
        online = mining = 0
        for pc, row in snapshot.items():
            values = row_values(pc, row, now)
            online += values[1] == 'BAĞLI'; mining += values[4] == 'ÇALIŞIYOR'
            if pc not in visible:
                continue
            tags = ('offline',) if values[1] == 'ÇEVRİMDIŞI' else ('mining',) if values[4] == 'ÇALIŞIYOR' else ()
            if self.table.exists(pc):
                self.table.item(pc, values=values, tags=tags)
            else:
                self.table.insert('', 'end', iid=pc, values=values, tags=tags)
        stop = 'AÇIK' if self.store.emergency_stop else 'KAPALI'
        self.summary.set(f'{len(snapshot)} BİLGİSAYAR   |   {online} BAĞLI   |   {mining} MINING   |   GENEL DURDURMA: {stop}')
        if schedule:
            self.root.after(1000, self.refresh)

    def fill_demo(self, now):
        for i, pc in enumerate(self.store.devices):
            if i % 13 == 0:
                continue
            active = (self.store.commands[pc]['desired_state'] == 'auto'
                      and not self.store.emergency_stop and i % 3 != 0)
            data = {'schema': 1, 'computer': pc, 'mining': active,
                    'reason': 'DEMO • Kilit eşleşmesi / bekleme örneği',
                    'vision': {'matched': i % 3 != 0, 'usable': i % 3 != 0},
                    'gpus': [{'temperature_c': 48 + i % 15}], 'oc_state': 'DEMO',
                    'estimated_profit_try_per_hour': {}, 'wait_remaining_seconds': 60 - int(now) % 60}
            self.store.heartbeat(pc, data, now)

    def close(self):
        # A closing/crashing panel leaves agents with no authenticated heartbeat;
        # they stop on their next unsuccessful exchange.
        self.store.command([], 'emergency')
        if self.server:
            self.server.shutdown(); self.server.server_close()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--self-test', action='store_true', help='Check the packaged demo GUI without a server')
    parser.add_argument('--config', type=Path, default=ROOT / 'panel_private/server.json')
    args = parser.parse_args()
    server = None
    if args.demo or args.self_test:
        profiles = [read_json(p) for p in sorted((ROOT / 'profiles').glob('*.json'))]
        store = PanelStore({p['worker']: {'gpu': p['gpu']} for p in profiles})
    else:
        if not args.config.exists() and args.config == ROOT / 'panel_private/server.json':
            from setup_panel import prepare
            prepare('http://192.168.1.77:8790', '192.168.1.77', root=ROOT)
        cfg = read_json(args.config)
        if cfg.get('schema') != 1 or len(cfg.get('devices', {})) != 79:
            raise ValueError('Expected private configuration for 79 computers; run setup_panel.py')
        state_path = Path(cfg['state_file']) if cfg.get('state_file') else None
        if state_path is not None and not state_path.is_absolute():
            state_path = ROOT / state_path
        store = PanelStore(cfg['devices'], state_path, cfg.get('state_storage_verified', False))
        server = serve(store, cfg['listen'], cfg['port'], cfg['certificate'], cfg['private_key'])
    try:
        root = tk.Tk(); panel = Panel(root, store, args.demo or args.self_test, server)
        if args.self_test:
            root.update_idletasks()
            if len(panel.table.get_children()) != 79:
                raise ValueError('Packaged GUI device list is incomplete')
            panel.close()
        else:
            root.mainloop()
    finally:
        if server:
            server.shutdown(); server.server_close()


if __name__ == '__main__':
    main()
