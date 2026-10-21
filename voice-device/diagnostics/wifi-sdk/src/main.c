// One explicit USB command, one radio attempt, no credentials or retry loop.
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_system.h"
#include "esp_heap_caps.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "esp_rom_sys.h"

#ifdef PROBE_LCD_SLEEP
#define PROBE_VARIANT "sdk-low-power-lcd-sleep"
static void lcd_command(uint8_t command) {
    gpio_set_level(8, 0); // Existing ST7789 CS/DC/MOSI/SCLK wiring.
    gpio_set_level(9, 0);
    for (unsigned mask=128; mask; mask>>=1) {
        gpio_set_level(12, 0);
        gpio_set_level(11, (command & mask) != 0);
        esp_rom_delay_us(2);
        gpio_set_level(12, 1);
        esp_rom_delay_us(2);
    }
    gpio_set_level(12, 0);
    gpio_set_level(8, 1);
    gpio_set_level(9, 1);
}
#else
#define PROBE_VARIANT "sdk-low-power"
#endif

_Static_assert(CONFIG_ESP_PHY_MAX_WIFI_TX_POWER == 10, "SDK PHY power cap missing");
_Static_assert(CONFIG_ESP_PHY_MAX_TX_POWER == 10, "PHY initialization table cap missing");
_Static_assert(CONFIG_ESP_PHY_REDUCE_TX_POWER == 1, "SDK brownout power reduction missing");
_Static_assert(CONFIG_ESP32S3_BROWNOUT_DET == 1, "Brownout protection must stay enabled");
_Static_assert(CONFIG_ESP32S3_BROWNOUT_DET_LVL == 7, "Keep production brownout threshold");
_Static_assert(CONFIG_ESP32S3_DEFAULT_CPU_FREQ_MHZ == 80, "Keep diagnostic CPU at 80 MHz");

static void report(const char *stage, esp_err_t result) {
    char line[512];
    int n = snprintf(line, sizeof(line),
        "{\"probe\":\"minimal-radio-1\",\"variant\":\"" PROBE_VARIANT "\",\"stage\":\"%s\","
        "\"result\":%d,\"result_name\":\"%s\",\"reset_reason\":%d,\"psram\":false,"
        "\"cpu_mhz\":80,\"phy_max_dbm\":%d,\"reduce_tx_power\":true,"
        "\"brownout_level\":%d,\"idf_version\":\"%s\",\"free_internal\":%u}\n",
        stage, (int)result, esp_err_to_name(result), (int)esp_reset_reason(),
        CONFIG_ESP_PHY_MAX_WIFI_TX_POWER, CONFIG_ESP32S3_BROWNOUT_DET_LVL,
        esp_get_idf_version(), (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
    fwrite(line, 1, n, stdout);
    fflush(stdout);
    vTaskDelay(pdMS_TO_TICKS(50));
}

static bool step(const char *name, esp_err_t result) {
    report(name, result);
    return result == ESP_OK;
}

static void run_probe(void) {
    report("begin", ESP_OK);
#ifdef PROBE_LCD_SLEEP
    lcd_command(0x28); // DISPOFF, then SLPIN. BLK supply is not switched.
    vTaskDelay(pdMS_TO_TICKS(10));
    lcd_command(0x10);
    vTaskDelay(pdMS_TO_TICKS(150));
    // Write-only SPI has no acknowledgement; do not claim measured power-off.
    report("lcd_sleep_requested", ESP_OK);
#endif
    if (!step("nvs_init", nvs_flash_init())) return; // Never erase existing NVS.
    if (!step("netif_init", esp_netif_init())) return;
    if (!step("event_loop", esp_event_loop_create_default())) return;
    if (!esp_netif_create_default_wifi_sta()) {report("sta_netif", ESP_ERR_NO_MEM); return;}
    wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
    if (!step("wifi_init", esp_wifi_init(&config))) return;
    if (!step("storage_ram", esp_wifi_set_storage(WIFI_STORAGE_RAM))) return;
    if (!step("set_mode", esp_wifi_set_mode(WIFI_MODE_STA))) return;
    report("before_wifi_start", ESP_OK);
    if (!step("wifi_start", esp_wifi_start())) return;
    // Runtime cap complements the SDK cap, but cannot affect initial RF start.
    if (!step("tx_power", esp_wifi_set_max_tx_power(34))) return;
    wifi_scan_config_t scan = {0};
    scan.channel = 1;
    scan.show_hidden = true;
    scan.scan_type = WIFI_SCAN_TYPE_PASSIVE;
    scan.scan_time.passive = 120;
    if (!step("passive_scan", esp_wifi_scan_start(&scan, true))) return;
    esp_wifi_clear_ap_list();
    step("wifi_stop", esp_wifi_stop());
    step("wifi_deinit", esp_wifi_deinit());
    report("complete", ESP_OK);
}

void app_main(void) {
    const int low[] = {4,5,11,12,15,16,17};
    const int high[] = {8,9,10};
    for (size_t i=0; i<sizeof(low)/sizeof(low[0]); ++i) {
        gpio_set_level(low[i], 0); gpio_set_direction(low[i], GPIO_MODE_OUTPUT);
    }
    for (size_t i=0; i<sizeof(high)/sizeof(high[0]); ++i) {
        gpio_set_level(high[i], 1); gpio_set_direction(high[i], GPIO_MODE_OUTPUT);
    }
    // Use the SDK console, including early startup/panic output, on native USB.
    fcntl(STDIN_FILENO, F_SETFL, O_NONBLOCK);
    char command[32] = {0};
    size_t used = 0;
    bool ran = false;
    TickType_t ready = 0;
    for (;;) {
        if (!ran && xTaskGetTickCount()-ready >= pdMS_TO_TICKS(1500)) {
            report("ready", ESP_OK); ready = xTaskGetTickCount();
        }
        char c;
        if (read(STDIN_FILENO, &c, 1) <= 0) {vTaskDelay(pdMS_TO_TICKS(20)); continue;}
        if (c=='\n') {
            if (!ran && !strcmp(command, "RUN_RADIO")) {ran=true; run_probe();}
            used=0; command[0]=0;
        } else if (c!='\r') {
            if (used<sizeof(command)-1) {command[used++]=c; command[used]=0;}
            else {used=0; command[0]=0;}
        }
    }
}
