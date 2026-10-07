"""Local screenshot/reference analysis. Image mismatch is UNKNOWN, not paid.

Pillow is imported lazily; bridge mode and pure policy tests need no image libs.
"""
import hashlib
import math
from pathlib import Path, PureWindowsPath
from signals import read_json, number


DEFAULT_REGIONS = [[.02, .02, .24, .22], [.76, .02, .98, .24],
                   [.02, .76, .24, .95], [.76, .76, .98, .95]]


def validate_calibration(doc):
    if doc.get('schema') != 1 or type(doc.get('verified')) is not bool:
        raise ValueError('Invalid vision calibration schema')
    if not isinstance(doc.get('expected_foreground_exe'), str):
        raise ValueError('Missing expected foreground process')
    regions = doc.get('regions')
    if not isinstance(regions, list) or len(regions) < 3 or len(regions) > 8:
        raise ValueError('Use 3 to 8 calibrated stable image regions')
    for rect in regions:
        if not isinstance(rect, list) or len(rect) != 4:
            raise ValueError('Invalid image region')
        x1, y1, x2, y2 = [number(x) for x in rect]
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1 and (x2-x1)*(y2-y1) >= .005):
            raise ValueError('Image region must be within the screenshot')
    for key, low, high in [('maximum_mean_error', 0, 20), ('maximum_rms_error', 0, 30),
                          ('maximum_tile_error', 0, 30), ('minimum_reference_deviation', 5, 80)]:
        if not low <= number(doc.get(key)) <= high:
            raise ValueError(f'Invalid {key}')
    return doc


def foreground_matches(actual, expected):
    return bool(expected and actual and PureWindowsPath(actual) == PureWindowsPath(expected))


def compare_images(frame, reference, calibration):
    from PIL import Image, ImageChops, ImageStat
    validate_calibration(calibration)
    if min(frame.size) < 300 or min(reference.size) < 300:
        raise ValueError('Screenshot/reference dimensions are too small')
    if abs((frame.width / frame.height) / (reference.width / reference.height) - 1) > .01:
        raise ValueError('Screen aspect ratio differs from reference; calibrate placement first')
    frame = frame.convert('RGB'); reference = reference.convert('RGB')
    metrics = []
    for rect in calibration['regions']:
        def patch(im):
            coords = tuple(round(n*s) for n, s in zip(rect, (im.width, im.height, im.width, im.height)))
            return im.crop(coords).resize((96, 64), Image.Resampling.LANCZOS)
        actual, expected = patch(frame), patch(reference)
        deviation = sum(ImageStat.Stat(expected).stddev) / 3
        difference = ImageChops.difference(actual, expected)
        stats = ImageStat.Stat(difference)
        mean, rms = sum(stats.mean)/3, sum(stats.rms)/3
        tile_errors = [sum(ImageStat.Stat(difference.crop((x, y, x+24, y+16))).mean)/3
                       for y in range(0, 64, 16) for x in range(0, 96, 24)]
        maximum_tile = max(tile_errors)
        passed = (deviation >= calibration['minimum_reference_deviation']
            and mean <= calibration['maximum_mean_error']
            and rms <= calibration['maximum_rms_error']
            and maximum_tile <= calibration['maximum_tile_error'])
        metrics.append({'mean_error': round(mean, 3), 'rms_error': round(rms, 3),
                        'maximum_tile_error': round(maximum_tile, 3),
                        'reference_deviation': round(deviation, 3), 'matched': passed})
    return {'matched': all(r['matched'] for r in metrics), 'regions': metrics,
            'frame_size': list(frame.size), 'reference_size': list(reference.size)}


class VisionReader:
    def __init__(self, root, worker):
        self.root, self.worker = Path(root), worker
        index = read_json(self.root / 'references/index.json')
        name = index['hosts'][worker]['image']
        if Path(name).name != name:
            raise ValueError('Unsafe reference image path')
        self.reference_path = self.root / 'references' / name
        raw = self.reference_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != index['images'][name]['sha256']:
            raise ValueError('Reference image SHA-256 mismatch')
        from PIL import Image
        with Image.open(self.reference_path) as image:
            self.reference = image.convert('RGB')
        self.calibration = validate_calibration(read_json(self.root / 'calibrations' / f'{worker}.json'))
        if self.calibration.get('computer') != worker:
            raise ValueError('Calibration belongs to a different computer')
        self.customer_reference = None
        customer = self.calibration.get('customer_reference')
        if customer is not None:
            if not isinstance(customer, dict) or not isinstance(customer.get('foreground_exes'), list):
                raise ValueError('Invalid customer-screen calibration')
            path = (self.root / customer['image']).resolve()
            if not path.is_relative_to(self.root.resolve()):
                raise ValueError('Customer reference must be inside the trusted installation')
            if hashlib.sha256(path.read_bytes()).hexdigest() != customer['sha256']:
                raise ValueError('Customer reference image SHA-256 mismatch')
            with Image.open(path) as image:
                self.customer_reference = image.convert('RGB')
        self.last_report = {'matched': False, 'usable': False, 'reason': 'No current capture'}

    def evaluate(self, frame, foreground, interactive):
        report = compare_images(frame, self.reference, self.calibration)
        verified = self.calibration['verified']
        process_ok = foreground_matches(foreground, self.calibration['expected_foreground_exe'])
        report.update({'verified': verified, 'foreground': foreground, 'foreground_matches': process_ok,
                       'usable': bool(report['matched'] and verified and process_ok and interactive)})
        customer_matched = False
        if self.customer_reference is not None:
            customer = compare_images(frame, self.customer_reference, self.calibration)
            allowed_exes = self.calibration['customer_reference']['foreground_exes']
            customer_matched = bool(customer['matched'] and verified and interactive
                and any(foreground_matches(foreground, exe) for exe in allowed_exes))
            report['customer_regions'] = customer['regions']
        report['customer_screen_matched'] = customer_matched
        if customer_matched and report['matched']:
            # Ambiguous references must never produce a free/occupied transition.
            report['usable'] = False; customer_matched = False
        report['session_occupied'] = False if report['usable'] else True if customer_matched else None
        report['reason'] = ('Lock image verified' if report['usable'] else
            'Calibration unverified' if not verified else 'Foreground/desktop not verified' if not process_ok or not interactive
            else 'Lock image not matched; session unknown')
        self.last_report = report
        return (report['session_occupied'], 0) if report['session_occupied'] is not None else (None, None)

    def read(self, api):
        try:
            from PIL import ImageGrab
            interactive, _ = api.input_state()
            before = api.foreground_executable()
            frame = ImageGrab.grab(include_layered_windows=True, all_screens=False)
            after = api.foreground_executable()
            # A foreground transition while capturing invalidates this sample.
            if not foreground_matches(before, after):
                raise ValueError('Foreground changed during capture')
            return self.evaluate(frame, after, interactive)
        except Exception as exc:
            self.last_report = {'matched': False, 'usable': False, 'reason': f'Capture blocked: {exc}'}
            return None, None
