#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import json
import os
import pathlib
import random
import re
import subprocess
import sys
from time import sleep

import common 


analysis_version = 8
max_images_to_analyze = 10

script_path, data_path = common.get_paths()
mnt_path = f'{data_path}mnt/'
lsb_path = f'{mnt_path}etc/lsb-release'
modules_path = pathlib.Path(f'{mnt_path}lib/modules/')
crostini_path = f'{mnt_path}usr/bin/crostini_client'
parallels_path = f'{mnt_path}opt/google/dlc/pita/package/imageloader.json'

with open(f'{data_path}android_versions.json', 'r') as f:
  android_versions = json.load(f)

pattern = f'{data_path}images/*/[0-9]*/*.json'
data_files = glob.glob(pattern)
i = 0
images_analyzed = 0
count = len(data_files)
for data_file in data_files:
  i += 1
  subprocess.run(['sudo', 'losetup', '--detach-all'])
  path = os.path.dirname(os.path.abspath(data_file))
  with open(data_file, 'r') as f:
    data = json.load(f)
  if data.get('analysis_version', 0) >= analysis_version:
    print(f'Analysis for {data_file} is up to date')
    continue
  else:
    data['analysis_version'] = analysis_version
  if data.get('md5'):
    backfill_verify = False
    verify = True
  else:
    backfill_verify = True
    verify = False
  print(f'analyzing image for {data["image_name"]}...')
  dl_results = common.download_image_file(data, path, backfill_verify=backfill_verify, verify=verify)
  if backfill_verify:
    data = dl_results['data']
  delete_download = dl_results.get('needed_to_download', False)
  image_file_path = dl_results.get('full_file_path')

  common.mount_image(image_file_path, mnt_path)

  # /etc/lsb-release contains interesting image details
  with open(lsb_path, 'r') as f:
    lsb_data = f.read().splitlines()
  for line in lsb_data:
    key, value = line.split('=')
    data[key.lower()] = value

  # /lib/modules/ subdirectories are the kernel version(s) of image
  data['linux_kernel_versions'] = [f.name for f in modules_path.iterdir() if f.is_dir()]

  # if chromeos_arc_android_sdk_version is set in /etc/lsb-release, Android apps are supported
  data['android_app_support'] = bool(data.get('chromeos_arc_android_sdk_version'))
  if data['android_app_support']:
    data['android_version'] = android_versions.get(data['chromeos_arc_android_sdk_version'], 'Unknown')

  # if /usr/sbin/crostini-client exists, Linux VMs are supported
  data['crostini_support'] = os.path.isfile(crostini_path)
  
  # if /opt/google/dlc/pita/package/imageloader.json exists, Parallels is supported in certain configs
  data['parallels_support'] = os.path.isfile(parallels_path)

  # Get EOL / AUE date of image
  hwclass_regex = random.choice(data['hwidmatches'])
  hardware_class = common.hwid_from_hwidmatch(hwclass_regex)
  print(f'hwid: {hardware_class}')
  update_data = common.check_updates(
      data['chromeos_board_appid'],
      data['version'],
      data['chromeos_release_board'],
      'stable-channel',
      hardware_class)
  data['sample_hwid'] = hardware_class
  data['aue_date'] = str(update_data.get('eol_date'))
  print(f'AUE date is {data["aue_date"]}')
  with open(data_file, 'w') as f:
    json.dump(data, f, indent=4, sort_keys=True)

  common.unmount_image(mnt_path)

  if delete_download:
    sleep(1)
    os.remove(image_file_path)
  analyzed_images += 1
  if analyzed_images >= max_images_to_analyze:
    print('Analyzed max 10 images. Breaking and we'll pickup where we left of next time...')
  
