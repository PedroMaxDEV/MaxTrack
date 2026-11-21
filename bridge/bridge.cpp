// Original MaxTrack transport. SDK declarations licensed by SCS Software.
#include <winsock2.h>
#include <windows.h>
#include <cmath>
#include <cstring>
#include "scssdk_input.h"

namespace {
SOCKET receiver = INVALID_SOCKET;
bool winsock = false;
constexpr unsigned axis_count = 4;
float axes[axis_count] = {};
float displayed[axis_count] = {};
ULONGLONG last_frame = 0;
unsigned next_axis = 0;
ULONGLONG last_packet = 0;
bool wants_window = false, outside = false;
bool switch_camera[2] = {};

void cleanup() {
    if (receiver != INVALID_SOCKET) closesocket(receiver);
    receiver = INVALID_SOCKET;
    if (winsock) WSACleanup();
    winsock = false;
    for (unsigned i = 0; i < axis_count; ++i) axes[i] = displayed[i] = 0;
    last_frame = 0;
    last_packet = 0;
    wants_window = outside = false;
    switch_camera[0] = switch_camera[1] = false;
}

SCSAPI_RESULT poll(scs_input_event_t* event, scs_u32_t flags, scs_context_t) {
    if (flags & SCS_INPUT_EVENT_CALLBACK_FLAG_first_in_frame) {
        next_axis = 0;
        // Bound work on the game main thread. Never wait on network I/O.
        for (unsigned i = 0; i < 64; ++i) {
            char buffer[49];
            int size = recv(receiver, buffer, sizeof(buffer), 0);
            if (size == SOCKET_ERROR) break;
            if (size != 48) continue;
            double values[6];
            std::memcpy(values, buffer, 48);
            if (!std::isfinite(values[3]) || !std::isfinite(values[4])) continue;
            if (std::abs(values[3]) > 180 || std::abs(values[4]) > 90) continue;
            axes[0] = static_cast<float>(values[3] / 180.0);
            axes[1] = static_cast<float>(values[4] / 90.0);
            axes[2] = std::isfinite(values[2]) && values[2] >= -.12 && values[2] <= 0
                ? static_cast<float>(values[2]) : 0;
            axes[3] = std::isfinite(values[0]) && std::abs(values[0]) <= .24
                ? static_cast<float>(values[0]) : 0;
            wants_window = values[5] == 1.0;
            last_packet = GetTickCount64();
        }
        const auto now = GetTickCount64();
        const bool stale = !last_packet || now - last_packet > 500;
        const bool target_window = !stale && wants_window;
        switch_camera[0] = !outside && target_window;
        switch_camera[1] = outside && !target_window;
        outside = target_window;
        const bool neutral = axes[0] == 0 && axes[1] == 0 && axes[2] == 0 && axes[3] == 0;
        const float alpha = !last_frame || neutral ? 1.f : 1.f - std::exp(-float(now - last_frame) / 22.f);
        for (unsigned i = 0; i < axis_count; ++i)
            displayed[i] = stale ? 0 : displayed[i] + alpha * (axes[i] - displayed[i]);
        last_frame = now;
    }
    if (next_axis >= axis_count + 2) return SCS_RESULT_not_found;
    event->input_index = next_axis;
    if (next_axis < axis_count) event->value_float.value = displayed[next_axis];
    else event->value_bool.value = switch_camera[next_axis - axis_count];
    ++next_axis;
    return SCS_RESULT_ok;
}
}

SCSAPI_RESULT scs_input_init(scs_u32_t version, const scs_input_init_params_t* params) {
    if (version != SCS_INPUT_VERSION_1_00) return SCS_RESULT_unsupported;
    if (!params) return SCS_RESULT_generic_error;
    cleanup();
    WSADATA data;
    if (WSAStartup(MAKEWORD(2,2), &data)) return SCS_RESULT_generic_error;
    winsock = true;
    receiver = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    BOOL exclusive = TRUE;
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(4243);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    u_long nonblocking = 1;
    if (receiver == INVALID_SOCKET ||
        setsockopt(receiver, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, reinterpret_cast<char*>(&exclusive), sizeof(exclusive)) ||
        bind(receiver, reinterpret_cast<sockaddr*>(&address), sizeof(address)) ||
        ioctlsocket(receiver, FIONBIO, &nonblocking)) {
        cleanup(); return SCS_RESULT_generic_error;
    }
    const auto* api = static_cast<const scs_input_init_params_v100_t*>(params);
    const scs_input_device_input_t inputs[] = {
        {"yaw", "Head yaw", SCS_VALUE_TYPE_float},
        {"pitch", "Head pitch", SCS_VALUE_TYPE_float},
        {"z", "Lean forward", SCS_VALUE_TYPE_float},
        {"x", "Lean sideways", SCS_VALUE_TYPE_float},
        {"window", "Driver window camera", SCS_VALUE_TYPE_bool},
        {"cabin", "Return to interior", SCS_VALUE_TYPE_bool}
    };
    scs_input_device_t device{};
    device.name = "maxtrack";
    device.display_name = "MaxTrack Pro Experimental";
    device.type = SCS_INPUT_DEVICE_TYPE_generic;
    device.input_count = axis_count + 2;
    device.inputs = inputs;
    device.input_event_callback = poll;
    auto result = api->register_device(&device);
    if (result != SCS_RESULT_ok) cleanup();
    else api->common.log(SCS_LOG_TYPE_message, "MaxTrack bridge: localhost UDP 4243; experimental camera binding required");
    return result;
}

SCSAPI_VOID scs_input_shutdown() { cleanup(); }
