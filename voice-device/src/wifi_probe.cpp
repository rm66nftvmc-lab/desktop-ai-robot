// Temporary, USB-triggered diagnostic only. No assets, I2S, credentials or retries.
#include <Arduino.h>
#include <esp_system.h>
#include <esp_heap_caps.h>
#include <esp_wifi.h>
#include <esp_wifi_default.h>
#include <esp_netif.h>
#include <esp_event.h>
#include <nvs_flash.h>
#include <esp_phy_init.h>

static bool ran=false;
static uint32_t lastReady=0;
static String command;

static void report(const char *stage,esp_err_t result=ESP_OK) {
  Serial.printf("{\"probe\":\"minimal-radio-1\",\"stage\":\"%s\",\"result\":%d,\"result_name\":\"%s\",\"reset_reason\":%d,\"psram\":%s,\"cpu_mhz\":%lu,\"free_internal\":%lu,\"largest_internal\":%lu}\n",
    stage,(int)result,esp_err_to_name(result),(int)esp_reset_reason(),psramFound()?"true":"false",
    (unsigned long)getCpuFrequencyMhz(),
    (unsigned long)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),
    (unsigned long)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
  Serial.flush();delay(30);
}

static bool step(const char *name,esp_err_t result,bool allowExisting=false) {
  report(name,result);
  return result==ESP_OK || (allowExisting && result==ESP_ERR_INVALID_STATE);
}

static void readCalibration() {
  ran=true;
  if(!step("nvs_init",nvs_flash_init()))return;
  esp_phy_calibration_data_t data;
  report("calibration_cache",esp_phy_load_cal_data_from_nvs(&data));
  // Report availability only. Never erase, print, fabricate or overwrite data.
  report("complete");
}

static void runProbe() {
  ran=true;
  setCpuFrequencyMhz(80);
  Serial.printf("{\"idf_version\":\"%s\"}\n",esp_get_idf_version());
  report("begin");
  if(!step("nvs_init",nvs_flash_init()))return; // Never erase the user's NVS.
  if(!step("netif_init",esp_netif_init(),true))return;
  if(!step("event_loop",esp_event_loop_create_default(),true))return;
  if(!esp_netif_create_default_wifi_sta()){report("sta_netif",ESP_ERR_NO_MEM);return;}
  report("before_wifi_init");
  wifi_init_config_t config=WIFI_INIT_CONFIG_DEFAULT();
  if(!step("wifi_init",esp_wifi_init(&config)))return;
  if(!step("storage_ram",esp_wifi_set_storage(WIFI_STORAGE_RAM)))return;
  if(!step("set_mode",esp_wifi_set_mode(WIFI_MODE_STA)))return;
  report("before_wifi_start");
  if(!step("wifi_start",esp_wifi_start()))return;
  if(!step("tx_power",esp_wifi_set_max_tx_power(34)))return; // 8.5 dBm.
  wifi_scan_config_t scan={};
  scan.channel=1;scan.show_hidden=true;scan.scan_type=WIFI_SCAN_TYPE_PASSIVE;
  scan.scan_time.passive=120;
  if(!step("passive_scan",esp_wifi_scan_start(&scan,true)))return;
  uint16_t count=0;
  esp_err_t result=esp_wifi_scan_get_ap_num(&count);
  Serial.printf("{\"scan_count\":%u}\n",count);
  if(!step("scan_count",result))return;
  esp_wifi_clear_ap_list();
  step("wifi_stop",esp_wifi_stop());
  step("wifi_deinit",esp_wifi_deinit());
  report("complete");
}

void setup() {
  // Preserve the existing wiring, but do not clock any attached peripheral.
  for(int pin:{4,5,11,12,15,16,17}){pinMode(pin,OUTPUT);digitalWrite(pin,LOW);}
  for(int pin:{8,9,10}){pinMode(pin,OUTPUT);digitalWrite(pin,HIGH);}
  Serial.begin(115200);
  command.reserve(32);
}

void loop() {
  if(Serial && !ran && millis()-lastReady>1500){report("ready");lastReady=millis();}
  while(Serial.available()) {
    char c=Serial.read();
    if(c=='\n') {
      if(!ran && command=="RUN_RADIO")runProbe();
      else if(!ran && command=="READ_CALIBRATION")readCalibration();
      command="";
    } else if(c!='\r') {
      if(command.length()<31)command+=c;else command="";
    }
  }
  delay(1);
}
