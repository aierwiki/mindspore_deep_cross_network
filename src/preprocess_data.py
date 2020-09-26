# Copyright 2020 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Download raw data and preprocessed data."""
import os
import pickle
import collections
import argparse
import numpy as np
from mindspore.mindrecord import FileWriter

#TRAIN_LINE_COUNT = 45840617
TRAIN_LINE_COUNT = 100000
TEST_LINE_COUNT = 6042135


class CriteoStatsDict():
    """preprocessed data"""

    def __init__(self):
        self.field_size = 39
        self.val_cols = ["val_{}".format(i + 1) for i in range(13)]
        self.cat_cols = ["cat_{}".format(i + 1) for i in range(26)]

        self.val_min_dict = {col: 0 for col in self.val_cols}
        self.val_max_dict = {col: 0 for col in self.val_cols}

        self.cat_count_dict = {col: collections.defaultdict(int) for col in self.cat_cols}

        self.oov_prefix = "OOV"

        self.cat2id_dict = {}
        self.cat2id_dict.update({col: i for i, col in enumerate(self.val_cols)})
        self.cat2id_dict.update(
            {self.oov_prefix + col: i + len(self.val_cols) for i, col in enumerate(self.cat_cols)})

    def stats_vals(self, val_list):
        """Handling weights column"""
        assert len(val_list) == len(self.val_cols)

        def map_max_min(i, val):
            key = self.val_cols[i]
            if val != "":
                if float(val) > self.val_max_dict[key]:
                    self.val_max_dict[key] = float(val)
                if float(val) < self.val_min_dict[key]:
                    self.val_min_dict[key] = float(val)

        for i, val in enumerate(val_list):
            map_max_min(i, val)

    def stats_cats(self, cat_list):
        """Handling cats column"""

        assert len(cat_list) == len(self.cat_cols)

        def map_cat_count(i, cat):
            key = self.cat_cols[i]
            self.cat_count_dict[key][cat] += 1

        for i, cat in enumerate(cat_list):
            map_cat_count(i, cat)

    def save_dict(self, dict_path, prefix=""):
        with open(os.path.join(dict_path, "{}val_max_dict.pkl".format(prefix)), "wb") as file_wrt:
            pickle.dump(self.val_max_dict, file_wrt)
        with open(os.path.join(dict_path, "{}val_min_dict.pkl".format(prefix)), "wb") as file_wrt:
            pickle.dump(self.val_min_dict, file_wrt)
        with open(os.path.join(dict_path, "{}cat_count_dict.pkl".format(prefix)), "wb") as file_wrt:
            pickle.dump(self.cat_count_dict, file_wrt)

    def load_dict(self, dict_path, prefix=""):
        with open(os.path.join(dict_path, "{}val_max_dict.pkl".format(prefix)), "rb") as file_wrt:
            self.val_max_dict = pickle.load(file_wrt)
        with open(os.path.join(dict_path, "{}val_min_dict.pkl".format(prefix)), "rb") as file_wrt:
            self.val_min_dict = pickle.load(file_wrt)
        with open(os.path.join(dict_path, "{}cat_count_dict.pkl".format(prefix)), "rb") as file_wrt:
            self.cat_count_dict = pickle.load(file_wrt)
        print("val_max_dict.items()[:50]:{}".format(list(self.val_max_dict.items())))
        print("val_min_dict.items()[:50]:{}".format(list(self.val_min_dict.items())))

    def get_cat2id(self, threshold=100):
        for key, cat_count_d in self.cat_count_dict.items():
            new_cat_count_d = dict(filter(lambda x: x[1] > threshold, cat_count_d.items()))
            for cat_str, _ in new_cat_count_d.items():
                self.cat2id_dict[key + "_" + cat_str] = len(self.cat2id_dict)
        print("cat2id_dict.size:{}".format(len(self.cat2id_dict)))
        print("cat2id.dict.items()[:50]:{}".format(list(self.cat2id_dict.items())[:50]))

    def map_cat2id(self, values, cats):
        """Cat to id"""

        def minmax_scale_value(i, val):
            max_v = float(self.val_max_dict["val_{}".format(i + 1)])
            return float(val) * 1.0 / max_v

        id_list = []
        weight_list = []
        for i, val in enumerate(values):
            if val == "":
                id_list.append(i)
                weight_list.append(0)
            else:
                key = "val_{}".format(i + 1)
                id_list.append(self.cat2id_dict[key])
                weight_list.append(minmax_scale_value(i, float(val)))

        for i, cat_str in enumerate(cats):
            key = "cat_{}".format(i + 1) + "_" + cat_str
            if key in self.cat2id_dict:
                id_list.append(self.cat2id_dict[key])
            else:
                id_list.append(self.cat2id_dict[self.oov_prefix + "cat_{}".format(i + 1)])
            weight_list.append(1.0)
        return id_list, weight_list


def mkdir_path(file_path):
    if not os.path.exists(file_path):
        os.makedirs(file_path)


def statsdata(file_path, dict_output_path, criteo_stats_dict):
    """Preprocess data and save data"""
    with open(file_path, encoding="utf-8") as file_in:
        errorline_list = []
        count = 0
        for line in file_in:
            count += 1
            line = line.strip("\n")
            items = line.split("\t")
            if len(items) != 40:
                errorline_list.append(count)
                print("line: {}".format(line))
                continue
            if count % 1000000 == 0:
                print("Have handled {}w lines.".format(count // 10000))
            values = items[1:14]
            cats = items[14:]

            assert len(values) == 13, "values.size: {}".format(len(values))
            assert len(cats) == 26, "cats.size: {}".format(len(cats))
            criteo_stats_dict.stats_vals(values)
            criteo_stats_dict.stats_cats(cats)
    criteo_stats_dict.save_dict(dict_output_path)


def random_split_trans2mindrecord(input_file_path, output_file_path, criteo_stats_dict, part_rows=2000000,
                                  line_per_sample=1000,
                                  test_size=0.1, seed=2020):
    """Random split data and save mindrecord"""
    test_size = int(TRAIN_LINE_COUNT * test_size)
    all_indices = [i for i in range(TRAIN_LINE_COUNT)]
    np.random.seed(seed)
    np.random.shuffle(all_indices)
    print("all_indices.size:{}".format(len(all_indices)))
    test_indices_set = set(all_indices[:test_size])
    print("test_indices_set.size:{}".format(len(test_indices_set)))
    print("-----------------------" * 10 + "\n" * 2)

    train_data_list = []
    test_data_list = []
    ids_list = []
    wts_list = []
    label_list = []

    writer_train = FileWriter(os.path.join(output_file_path, "train_input_part.mindrecord"), 21)
    writer_test = FileWriter(os.path.join(output_file_path, "test_input_part.mindrecord"), 3)

    schema = {"label": {"type": "float32", "shape": [-1]}, "feat_vals": {"type": "float32", "shape": [-1]},
              "feat_ids": {"type": "int32", "shape": [-1]}}
    writer_train.add_schema(schema, "CRITEO_TRAIN")
    writer_test.add_schema(schema, "CRITEO_TEST")

    with open(input_file_path, encoding="utf-8") as file_in:
        items_error_size_lineCount = []
        count = 0
        train_part_number = 0
        test_part_number = 0
        for i, line in enumerate(file_in):
            count += 1
            if count % 1000000 == 0:
                print("Have handle {}w lines.".format(count // 10000))
            line = line.strip("\n")
            items = line.split("\t")
            if len(items) != 40:
                items_error_size_lineCount.append(i)
                continue
            label = float(items[0])
            values = items[1:14]
            cats = items[14:]

            assert len(values) == 13, "values.size: {}".format(len(values))
            assert len(cats) == 26, "cats.size: {}".format(len(cats))

            ids, wts = criteo_stats_dict.map_cat2id(values, cats)

            ids_list.extend(ids)
            wts_list.extend(wts)
            label_list.append(label)

            if count % line_per_sample == 0:
                if i not in test_indices_set:
                    train_data_list.append({"feat_ids": np.array(ids_list, dtype=np.int32),
                                            "feat_vals": np.array(wts_list, dtype=np.float32),
                                            "label": np.array(label_list, dtype=np.float32)
                                            })
                else:
                    test_data_list.append({"feat_ids": np.array(ids_list, dtype=np.int32),
                                           "feat_vals": np.array(wts_list, dtype=np.float32),
                                           "label": np.array(label_list, dtype=np.float32)
                                           })
                if train_data_list and len(train_data_list) % part_rows == 0:
                    writer_train.write_raw_data(train_data_list)
                    train_data_list.clear()
                    train_part_number += 1

                if test_data_list and len(test_data_list) % part_rows == 0:
                    writer_test.write_raw_data(test_data_list)
                    test_data_list.clear()
                    test_part_number += 1

                ids_list.clear()
                wts_list.clear()
                label_list.clear()

        if train_data_list:
            writer_train.write_raw_data(train_data_list)
        if test_data_list:
            writer_test.write_raw_data(test_data_list)
    writer_train.commit()
    writer_test.commit()

    print("------" * 5)
    print("items_error_size_lineCount.size(): {}.".format(len(items_error_size_lineCount)))
    print("------" * 5)
    np.save(os.path.join(output_file_path, "items_error_size_lineCount.npy"), items_error_size_lineCount)


def main(data_path, data_file="train_medium.txt"):
    criteo_stats = CriteoStatsDict()
    data_file_path = os.path.join(data_path, "origin_data", data_file)
    stats_output_path = os.path.join(data_path, "stats_dict")
    mkdir_path(stats_output_path)
    statsdata(data_file_path, stats_output_path, criteo_stats)

    criteo_stats.load_dict(dict_path=stats_output_path, prefix="")
    criteo_stats.get_cat2id(threshold=10)
    in_file_path = os.path.join(data_path, "origin_data", data_file)
    output_path = os.path.join(data_path, "mindrecord")
    mkdir_path(output_path)
    random_split_trans2mindrecord(in_file_path, output_path, criteo_stats, part_rows=2000000, line_per_sample=1000,
                                  test_size=0.1, seed=2020)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="criteo data")
    parser.add_argument("--data_path", type=str, default="./criteo_data/")

    args, _ = parser.parse_known_args()
    data_path = args.data_path
    main(data_path)
    

    