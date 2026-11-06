import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import region_lookup


def directory():
    return {'environment': 'test', 'retrieved_at': '2026-11-06', 'nodes': [
        {'id': 'z', 'parent_id': '0', 'name': '浙江省', 'level': 'province'},
        {'id': 'h', 'parent_id': 'z', 'name': '杭州市', 'level': 'city'},
        {'id': 'x', 'parent_id': 'h', 'name': '西湖区', 'level': 'district'},
        {'id': 'b', 'parent_id': '0', 'name': '北京市', 'level': 'province'},
        {'id': 'bc', 'parent_id': 'b', 'name': '北京市', 'level': 'city'},
        {'id': 'hd', 'parent_id': 'bc', 'name': '海淀区', 'level': 'district'},
    ]}


class RegionPrepareTests(unittest.TestCase):
    def prepare(self, **fields):
        return region_lookup.lookup({'op': 'prepare', 'environment': 'test', **fields}, directory())

    def test_full_and_short_names_have_identical_canonical_paths(self):
        for names in (['浙江省', '杭州市', '西湖区'], ['浙江', '杭州', '西湖']):
            with self.subTest(names=names):
                result = self.prepare(names=names, detail='文三路 1 号，2幢 ３单元')
                self.assertTrue(result['ok'], result)
                self.assertEqual(result['region_id_path'], 'z,h,x')
                self.assertEqual(result['region_path'], '浙江省,杭州市,西湖区')
                self.assertEqual(result['detail'], '文三路 1 号，2幢 ３单元')

    def test_fourth_name_is_preserved_as_detail_without_fourth_id(self):
        for detail in ('文三路1号', '翠苑街道文三路1号'):
            result = self.prepare(names=['浙江', '杭州', '西湖', '翠苑街道'], detail=detail)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['ids'], ['z', 'h', 'x'])
            self.assertEqual(result['detail'], '翠苑街道文三路1号')

    def test_full_address_removes_only_three_regions(self):
        for address in ('浙江省杭州市西湖区翠苑街道文三路1号',
                        '浙江 杭州 西湖 翠苑街道文三路1号',
                        '浙江省，杭州市，西湖区，翠苑街道文三路1号'):
            with self.subTest(address=address):
                result = self.prepare(address=address)
                self.assertTrue(result['ok'], result)
                self.assertEqual(result['detail'], '翠苑街道文三路1号')

    def test_municipality_can_omit_repeated_city_name(self):
        result = self.prepare(address='北京市海淀区中关村街道测试路1号')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['names'], ['北京市', '北京市', '海淀区'])
        self.assertEqual(result['detail'], '中关村街道测试路1号')

    def test_unclear_short_district_boundary_requires_clarification(self):
        result = self.prepare(address='浙江杭州西湖大学路1号')
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'REGION_BOUNDARY_UNCLEAR')

    def test_ambiguous_alias_returns_candidates_instead_of_picking_one(self):
        data = directory()
        data['nodes'].append({'id': 'x2', 'parent_id': 'h', 'name': '西湖县', 'level': 'district'})
        result = region_lookup.lookup({'op': 'prepare', 'environment': 'test', 'names': ['浙江', '杭州', '西湖']}, data)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'REGION_NOT_UNIQUE')
        self.assertEqual(len(result['candidates']), 2)
        exact = region_lookup.lookup({'op': 'prepare', 'environment': 'test', 'names': ['浙江', '杭州', '西湖区']}, data)
        self.assertEqual(exact['ids'], ['z', 'h', 'x'])

    def test_missing_detail_is_reported_without_inventing_a_street(self):
        result = self.prepare(names=['浙江', '杭州', '西湖'])
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['detail_required'])
        self.assertEqual(result['detail'], '')

    def test_fourth_name_without_detail_still_requires_detail(self):
        for fields in ({}, {'detail': ''}, {'detail': '翠苑街道'}):
            result = self.prepare(names=['浙江', '杭州', '西湖', '翠苑街道'], **fields)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['detail'], '翠苑街道')
            self.assertTrue(result['detail_required'])

    def test_raw_address_with_only_street_still_requires_detail(self):
        result = self.prepare(address='浙江省杭州市西湖区翠苑街道')
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['detail_required'])

    def test_fullwidth_spaces_between_regions_are_boundaries(self):
        result = self.prepare(address='浙江　杭州　西湖　翠苑街道文三路1号')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['detail'], '翠苑街道文三路1号')

    def test_environment_mismatch_cannot_relabel_pre_as_prod(self):
        data = directory()
        data['environment'] = 'pre'
        result = region_lookup.lookup({'op': 'prepare', 'environment': 'prod', 'names': ['浙江', '杭州', '西湖']}, data)
        self.assertEqual(result['error'], 'ENVIRONMENT_MISMATCH')

    def test_conflicting_or_malformed_inputs_are_rejected(self):
        for fields in ({'names': ['浙江', '杭州', '西湖'], 'address': '浙江省杭州市西湖区'},
                       {'names': ['浙江', '杭州', '西湖'], 'detail': 123},
                       {'names': ['浙江', '', '西湖']},
                       {'address': '浙江省杭州市西湖区测试路', 'detail': '另一条路'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.prepare(**fields)

    def test_id_path_must_follow_parent_relations(self):
        result = region_lookup.lookup({'op': 'resolve', 'environment': 'test', 'ids': ['z', 'bc', 'hd']}, directory())
        self.assertFalse(result['ok'])

    def test_same_district_name_in_other_city_does_not_affect_parent_scoped_lookup(self):
        data = directory()
        data['nodes'].extend([
            {'id': 'c2', 'parent_id': 'z', 'name': '测试市', 'level': 'city'},
            {'id': 'd2', 'parent_id': 'c2', 'name': '西湖区', 'level': 'district'},
        ])
        result = region_lookup.lookup({'op': 'prepare', 'environment': 'test', 'names': ['浙江', '杭州', '西湖']}, data)
        self.assertEqual(result['ids'], ['z', 'h', 'x'])

    def test_missing_province_in_full_text_is_not_guessed(self):
        result = self.prepare(address='杭州市西湖区测试路1号')
        self.assertFalse(result['ok'])
        self.assertEqual(result['level'], 'province')

    def test_directory_with_duplicate_ids_or_broken_parents_is_rejected(self):
        for broken in ('duplicate', 'parent'):
            data = directory()
            if broken == 'duplicate':
                data['nodes'].append(dict(data['nodes'][0]))
            else:
                data['nodes'][1]['parent_id'] = 'missing'
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                region_lookup.lookup({'op': 'prepare', 'environment': 'test', 'names': ['浙江', '杭州', '西湖']}, data)

    def test_autonomous_region_alias_and_district_internal_characters(self):
        data = {'environment': 'test', 'nodes': [
            {'id': 'p', 'parent_id': '0', 'name': '广西壮族自治区', 'level': 'province'},
            {'id': 'c', 'parent_id': 'p', 'name': '测试市', 'level': 'city'},
            {'id': 'd', 'parent_id': 'c', 'name': '市中区', 'level': 'district'},
        ]}
        result = region_lookup.lookup({'op': 'prepare', 'environment': 'test', 'names': ['广西', '测试', '市中']}, data)
        self.assertEqual(result['names'], ['广西壮族自治区', '测试市', '市中区'])

    def test_autonomous_prefecture_county_and_banner_short_names(self):
        for city, district, short_city, short_district in (
            ('延边朝鲜族自治州', '延吉市', '延边', '延吉'),
            ('恩施土家族苗族自治州', '恩施市', '恩施', '恩施'),
            ('伊犁哈萨克自治州', '察布查尔锡伯自治县', '伊犁', '察布查尔'),
            ('测试市', '长阳土家族自治县', '测试', '长阳'),
            ('测试市', '莫力达瓦达斡尔族自治旗', '测试', '莫力达瓦'),
            ('测试市', '鄂温克族自治旗', '测试', '鄂温克'),
            ('测试市', '龙胜各族自治县', '测试', '龙胜'),
        ):
            data = directory()
            data['nodes'][1]['name'] = city
            data['nodes'][2]['name'] = district
            with self.subTest(city=city, district=district):
                result = region_lookup.lookup({'environment': 'test', 'names': ['浙江', short_city, short_district], 'detail': '测试路1号'}, data)
                self.assertTrue(result['ok'], result)
                self.assertEqual(result['names'], ['浙江省', city, district])
                self.assertEqual(result['region_id_path'], 'z,h,x')

    def test_autonomous_short_city_in_raw_address_keeps_detail(self):
        data = directory()
        data['nodes'][1]['name'] = '延边朝鲜族自治州'
        data['nodes'][2]['name'] = '延吉市'
        result = region_lookup.lookup({'environment': 'test', 'address': '浙江延边延吉市测试路 1 号'}, data)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['detail'], '测试路 1 号')

    def test_new_autonomous_aliases_do_not_pick_between_multiple_candidates(self):
        data = directory()
        data['nodes'][1]['name'] = '大理白族自治州'
        data['nodes'].append({'id': 'h2', 'parent_id': 'z', 'name': '大理彝族自治州', 'level': 'city'})
        result = region_lookup.lookup({'environment': 'test', 'names': ['浙江', '大理', '西湖']}, data)
        self.assertEqual(result['error'], 'REGION_NOT_UNIQUE')
        self.assertEqual({n['id'] for n in result['candidates']}, {'h', 'h2'})

    def test_raw_address_prefers_full_name_over_another_nodes_alias(self):
        data = directory()
        data['nodes'].append({'id': 'x2', 'parent_id': 'h', 'name': '西湖区县', 'level': 'district'})
        result = region_lookup.lookup({'environment': 'test', 'address': '浙江省杭州市西湖区测试路1号'}, data)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['ids'], ['z', 'h', 'x'])

    def test_wrong_suffix_and_arbitrary_substrings_are_not_matched(self):
        for names in (['浙江市', '杭州', '西湖'], ['浙江', '杭', '西湖'], ['浙江', '杭州', '湖']):
            with self.subTest(names=names):
                self.assertFalse(self.prepare(names=names)['ok'])

    def test_cli_accepts_an_explicit_environment_bound_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'regions.json'
            source.write_text(json.dumps(directory(), ensure_ascii=False), encoding='utf8')
            result = subprocess.run([sys.executable, '-B', '-X', 'utf8', region_lookup.__file__, '--data-file', str(source)],
                                    input=json.dumps({'op': 'prepare', 'environment': 'test', 'names': ['浙江', '杭州', '西湖'], 'detail': '测试路1号'}),
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(result.stdout)['region_id_path'], 'z,h,x')


if __name__ == '__main__':
    unittest.main()
