#include "bridge.cpp"
#include <cassert>
#include <cstdio>

scs_input_event_callback_t callback = nullptr;
SCSAPI_RESULT capture(const scs_input_device_t* device) {
    assert(device->input_count == 6);
    assert(std::strcmp(device->name, "maxtrack") == 0);
    callback = device->input_event_callback;
    return SCS_RESULT_ok;
}
SCSAPI_VOID log_message(scs_log_type_t, scs_string_t) {}

int main() {
    scs_input_init_params_v100_t params{};
    params.common.log = log_message;
    params.register_device = capture;
    assert(scs_input_init(0, &params) == SCS_RESULT_unsupported);
    assert(scs_input_init(SCS_INPUT_VERSION_1_00, nullptr) == SCS_RESULT_generic_error);
    assert(scs_input_init(SCS_INPUT_VERSION_1_00, &params) == SCS_RESULT_ok);
    SOCKET sender = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    sockaddr_in target{};
    target.sin_family = AF_INET;
    target.sin_port = htons(4243);
    target.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    double pose[6] = {-.12,0,-.1,90,-45,1};
    assert(sendto(sender, reinterpret_cast<char*>(pose), sizeof(pose), 0,
        reinterpret_cast<sockaddr*>(&target), sizeof(target)) == 48);
    Sleep(20);
    scs_input_event_t event{};
    assert(callback(&event, 1, nullptr) == 0);
    assert(event.input_index == 0 && event.value_float.value == .5f);
    assert(callback(&event, 0, nullptr) == 0);
    assert(event.input_index == 1 && event.value_float.value == -.5f);
    assert(callback(&event, 0, nullptr) == 0);
    assert(event.input_index == 2 && event.value_float.value == -.1f);
    assert(callback(&event, 0, nullptr) == 0);
    assert(event.input_index == 3 && event.value_float.value == -.12f);
    assert(callback(&event, 0, nullptr) == 0 && event.input_index == 4 && event.value_bool.value == 1);
    assert(callback(&event, 0, nullptr) == 0 && event.input_index == 5 && event.value_bool.value == 0);
    assert(callback(&event, 0, nullptr) == SCS_RESULT_not_found);
    assert(callback(&event, 1, nullptr) == 0);
    for (int index = 1; index <= 4; ++index) assert(callback(&event, 0, nullptr) == 0);
    assert(event.input_index == 4 && event.value_bool.value == 0);
    pose[3] = NAN;
    sendto(sender, reinterpret_cast<char*>(pose), sizeof(pose), 0,
        reinterpret_cast<sockaddr*>(&target), sizeof(target));
    Sleep(20);
    assert(callback(&event, 1, nullptr) == 0 && event.value_float.value == .5f);
    Sleep(550);
    assert(callback(&event, 1, nullptr) == 0 && event.value_float.value == 0);
    for (int index = 1; index <= 5; ++index) assert(callback(&event, 0, nullptr) == 0);
    assert(event.input_index == 5 && event.value_bool.value == 1);
    closesocket(sender);
    scs_input_shutdown();
    assert(scs_input_init(SCS_INPUT_VERSION_1_00, &params) == 0);
    scs_input_shutdown();
    puts("PASS: SDK registration, UDP axes, NaN rejection, timeout, restart");
}
