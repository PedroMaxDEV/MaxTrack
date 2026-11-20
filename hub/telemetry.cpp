#include <winsock2.h>
#include <windows.h>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include "scssdk_telemetry.h"
#include "common/scssdk_telemetry_common_configs.h"
#include "common/scssdk_telemetry_common_channels.h"
#include "common/scssdk_telemetry_truck_common_channels.h"

namespace {
SOCKET output = INVALID_SOCKET;
sockaddr_in destination{};
ULONGLONG last_send = 0;
double local_scale, speed, distance, seconds, limit, x, z, heading;
double fuel, fuel_capacity, rpm, cruise, odometer, wear;
int gear;
unsigned long long income;
std::string truck, cargo, origin, delivery, city_id, company_id;
bool positioned = false, paused = true;

void close_output() {
    if (output != INVALID_SOCKET) closesocket(output);
    output = INVALID_SOCKET;
    WSACleanup();
}

SCSAPI_VOID number(scs_string_t, scs_u32_t, const scs_value_t* value, scs_context_t context) {
    *static_cast<double*>(context) = value && std::isfinite(value->value_float.value)
        ? value->value_float.value : -1;
}

SCSAPI_VOID position(scs_string_t, scs_u32_t, const scs_value_t* value, scs_context_t) {
    positioned = false;
    if (!value) return;
    const auto& placement = value->value_dplacement;
    x = placement.position.x;
    z = placement.position.z;
    heading = placement.orientation.heading;
    positioned = std::isfinite(x) && std::isfinite(z) && std::isfinite(heading);
}

SCSAPI_VOID gear_value(scs_string_t, scs_u32_t, const scs_value_t* value, scs_context_t) {
    gear = value ? value->value_s32.value : 0;
}

std::string json_string(const std::string& value) {
    std::string result = "\"";
    for (unsigned char ch : value) {
        if (ch == '"' || ch == '\\') result += '\\';
        if (ch >= 32) result += static_cast<char>(ch);
    }
    return result + '"';
}

SCSAPI_VOID configuration(scs_event_t, const void* info, scs_context_t) {
    const auto* cfg = static_cast<const scs_telemetry_configuration_t*>(info);
    const bool is_truck = std::strcmp(cfg->id, SCS_TELEMETRY_CONFIG_truck) == 0;
    const bool is_job = std::strcmp(cfg->id, SCS_TELEMETRY_CONFIG_job) == 0;
    if (!is_truck && !is_job) return;
    if (is_job) { cargo.clear(); origin.clear(); delivery.clear(); city_id.clear(); company_id.clear(); income = 0; }
    if (is_truck) { truck.clear(); fuel_capacity = -1; }
    for (const auto* attr = cfg->attributes; attr && attr->name; ++attr) {
        const auto& value = attr->value;
        const auto named = [&](const char* name) { return std::strcmp(attr->name, name) == 0; };
        if (value.type == SCS_VALUE_TYPE_string && value.value_string.value) {
            const std::string text(value.value_string.value);
            if (is_truck && named(SCS_TELEMETRY_CONFIG_ATTRIBUTE_name)) truck = text;
            if (is_job && named(SCS_TELEMETRY_CONFIG_ATTRIBUTE_cargo)) cargo = text;
            if (is_job && named(SCS_TELEMETRY_CONFIG_ATTRIBUTE_source_city)) origin = text;
            if (is_job && named(SCS_TELEMETRY_CONFIG_ATTRIBUTE_destination_company_id)) company_id = text;
            if (is_job && named(SCS_TELEMETRY_CONFIG_ATTRIBUTE_destination_city_id)) city_id = text;
            if (is_job && named(SCS_TELEMETRY_CONFIG_ATTRIBUTE_destination_city)) delivery = text;
        }
        if (is_truck && value.type == SCS_VALUE_TYPE_float && named(SCS_TELEMETRY_CONFIG_ATTRIBUTE_fuel_capacity))
            fuel_capacity = std::isfinite(value.value_float.value) ? value.value_float.value : -1;
        if (is_job && value.type == SCS_VALUE_TYPE_u64 && named(SCS_TELEMETRY_CONFIG_ATTRIBUTE_income))
            income = value.value_u64.value;
    }
}

SCSAPI_VOID pause_state(scs_event_t event, const void*, scs_context_t) {
    paused = event == SCS_TELEMETRY_EVENT_paused;
}

SCSAPI_VOID frame(scs_event_t, const void*, scs_context_t) {
    const auto now = GetTickCount64();
    if (output == INVALID_SOCKET || !positioned || now - last_send < 150) return;
    last_send = now;
    char numbers[768];
    const int size = std::snprintf(numbers, sizeof(numbers),
        "{\"speed\":%.3f,\"distance\":%.3f,\"seconds\":%.3f,\"limit\":%.3f,\"x\":%.3f,\"z\":%.3f,\"heading\":%.5f,"
        "\"fuel\":%.2f,\"fuelCapacity\":%.2f,\"rpm\":%.1f,\"cruise\":%.3f,\"odometer\":%.2f,\"wear\":%.5f,"
        "\"localScale\":%.3f,\"gear\":%d,\"income\":%llu,\"paused\":%s",
        speed, distance, seconds, limit, x, z, heading, fuel, fuel_capacity, rpm, cruise, odometer, wear,
        local_scale, gear, income, paused ? "true" : "false");
    if (size < 1 || size >= sizeof(numbers)) return;
    const std::string payload = std::string(numbers, size) + ",\"truckName\":" + json_string(truck) +
        ",\"cargo\":" + json_string(cargo) + ",\"origin\":" + json_string(origin) +
        ",\"delivery\":" + json_string(delivery) + ",\"cityId\":" + json_string(city_id) +
        ",\"companyId\":" + json_string(company_id) + '}';
    if (payload.size() <= 8192)
        sendto(output, payload.data(), static_cast<int>(payload.size()), 0,
            reinterpret_cast<const sockaddr*>(&destination), sizeof(destination));
}
}

SCSAPI_RESULT scs_telemetry_init(scs_u32_t version, const scs_telemetry_init_params_t* params) {
    if (version != SCS_TELEMETRY_VERSION_1_00 && version != SCS_TELEMETRY_VERSION_1_01)
        return SCS_RESULT_unsupported;
    if (!params) return SCS_RESULT_generic_error;
    const auto* sdk = static_cast<const scs_telemetry_init_params_v100_t*>(params);
    local_scale = speed = distance = seconds = limit = -1;
    fuel = fuel_capacity = rpm = cruise = odometer = wear = -1;
    gear = 0;
    income = 0;
    truck.clear(); cargo.clear(); origin.clear(); delivery.clear(); city_id.clear(); company_id.clear();
    positioned = false;
    paused = true;
    last_send = 0;
    WSADATA data{};
    if (WSAStartup(MAKEWORD(2, 2), &data)) return SCS_RESULT_generic_error;
    output = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    unsigned long nonblocking = 1;
    destination.sin_family = AF_INET;
    destination.sin_port = htons(4244);
    destination.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    constexpr auto flags = SCS_TELEMETRY_CHANNEL_FLAG_no_value;
    if (output == INVALID_SOCKET || ioctlsocket(output, FIONBIO, &nonblocking) ||
        sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_world_placement, SCS_U32_NIL,
            SCS_VALUE_TYPE_dplacement, flags, position, nullptr) != SCS_RESULT_ok ||
        sdk->register_for_event(SCS_TELEMETRY_EVENT_frame_end, frame, nullptr) != SCS_RESULT_ok) {
        close_output();
        return SCS_RESULT_generic_error;
    }
    sdk->register_for_channel(SCS_TELEMETRY_CHANNEL_local_scale, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &local_scale);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_speed, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &speed);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_navigation_distance, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &distance);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_navigation_time, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &seconds);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_navigation_speed_limit, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &limit);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_fuel, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &fuel);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_engine_rpm, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &rpm);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_cruise_control, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &cruise);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_odometer, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &odometer);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_wear_engine, SCS_U32_NIL, SCS_VALUE_TYPE_float, flags, number, &wear);
    sdk->register_for_channel(SCS_TELEMETRY_TRUCK_CHANNEL_engine_gear, SCS_U32_NIL, SCS_VALUE_TYPE_s32, flags, gear_value, nullptr);
    sdk->register_for_event(SCS_TELEMETRY_EVENT_configuration, configuration, nullptr);
    sdk->register_for_event(SCS_TELEMETRY_EVENT_paused, pause_state, nullptr);
    sdk->register_for_event(SCS_TELEMETRY_EVENT_started, pause_state, nullptr);
    sdk->common.log(SCS_LOG_TYPE_message, "Max GPS: localhost UDP 4244");
    return SCS_RESULT_ok;
}

SCSAPI_VOID scs_telemetry_shutdown() {
    close_output();
}
