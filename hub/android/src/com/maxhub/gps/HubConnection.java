package com.maxhub.gps;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.Inet4Address;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.URI;
import java.net.Proxy;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class HubConnection {
    static final int MAX_MAP = 32 * 1024 * 1024;
    final URI origin;
    final String token;
    final String name;

    HubConnection(String host, int port, String token, String name) {
        this.origin = URI.create("http://" + host + ":" + port);
        this.token = token;
        this.name = name;
    }

    static boolean privateIp(String host) {
        return host != null && host.matches("(?:[0-9]{1,3}\\.){3}[0-9]{1,3}")
                && isPrivate(host.split("\\."));
    }

    private static boolean isPrivate(String[] parts) {
        for (String part : parts) if (Integer.parseInt(part) > 255) return false;
        int a = Integer.parseInt(parts[0]), b = Integer.parseInt(parts[1]);
        return a == 10 || (a == 192 && b == 168) || (a == 172 && b >= 16 && b <= 31);
    }

    static HubConnection parse(String address) {
        try {
            URI uri = URI.create(address.trim());
            if (!"http".equals(uri.getScheme()) || !privateIp(uri.getHost()) || uri.getUserInfo() != null ||
                    uri.getPort() < 1 || uri.getPort() > 65535) return null;
            String token = android.net.Uri.parse(address).getQueryParameter("chave");
            if (token == null || !token.matches("[A-Za-z0-9_-]{16,64}")) return null;
            return new HubConnection(uri.getHost(), uri.getPort(), token, uri.getHost());
        } catch (RuntimeException ex) { return null; }
    }

    String address() { return origin + "/?chave=" + token; }

    static List<HubConnection> discover() throws IOException {
        String nonce = String.format(Locale.ROOT, "%016x", new SecureRandom().nextLong());
        byte[] message = ("MAXGPS/1 " + nonce).getBytes(StandardCharsets.US_ASCII);
        Map<String, HubConnection> replies = new LinkedHashMap<>();
        try (DatagramSocket socket = new DatagramSocket()) {
            socket.setBroadcast(true);
            socket.setSoTimeout(320);
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            while (interfaces != null && interfaces.hasMoreElements()) {
                NetworkInterface network = interfaces.nextElement();
                if (!network.isUp()) continue;
                for (InterfaceAddress item : network.getInterfaceAddresses()) {
                    InetAddress broadcast = item.getBroadcast();
                    if (broadcast instanceof Inet4Address && privateIp(item.getAddress().getHostAddress())) {
                        try { socket.send(new DatagramPacket(message, message.length, broadcast, 8766)); }
                        catch (IOException ignored) {}
                    }
                }
            }
            try { socket.send(new DatagramPacket(message, message.length, InetAddress.getByName("255.255.255.255"), 8766)); }
            catch (IOException ignored) {}
            long deadline = android.os.SystemClock.elapsedRealtime() + 2100;
            byte[] buffer = new byte[512];
            while (android.os.SystemClock.elapsedRealtime() < deadline) {
                DatagramPacket received = new DatagramPacket(buffer, buffer.length);
                try {
                    socket.receive(received);
                    String host = received.getAddress().getHostAddress();
                    JSONObject data = new JSONObject(new String(buffer, 0, received.getLength(), StandardCharsets.UTF_8));
                    int port = data.optInt("port");
                    if (privateIp(host) && received.getPort() == 8766 && port > 0 && port <= 65535 &&
                            nonce.equals(data.optString("nonce")) && "MaxHub".equals(data.optString("service"))) {
                        replies.put(host+":"+port, new HubConnection(host, port, "", data.optString("name", host)));
                    }
                } catch (SocketTimeoutException | org.json.JSONException ignored) {}
            }
        }
        return new ArrayList<>(replies.values());
    }

    HubConnection pair(String code) throws Exception {
        JSONObject data = new JSONObject().put("code", code);
        JSONObject reply = json("/parear", data);
        String issued = reply.getString("token");
        if (!issued.matches("[A-Za-z0-9_-]{16,64}")) throw new IOException("Token inválido");
        return new HubConnection(origin.getHost(), origin.getPort(), issued, reply.optString("name", name));
    }

    JSONObject json(String path, JSONObject body) throws Exception {
        return new JSONObject(new String(request(path,body,256*1024), StandardCharsets.UTF_8));
    }

    byte[] request(String path, JSONObject body, int limit) throws IOException {
        HttpURLConnection connection = (HttpURLConnection)origin.resolve(path).toURL().openConnection(Proxy.NO_PROXY);
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(2100);
        connection.setReadTimeout(path.startsWith("/voz/") ? 22000 : limit == MAX_MAP ? 45000 : body == null ? 2800 : 7500);
        if (!token.isEmpty()) connection.setRequestProperty("X-MaxGPS-Key", token);
        connection.setRequestProperty("Accept","application/json");
        try {
            if (body != null) {
                connection.setRequestMethod("POST");
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type","application/json");
                try (OutputStream out = connection.getOutputStream()) {
                    out.write(body.toString().getBytes(StandardCharsets.UTF_8));
                }
            }
            int status = connection.getResponseCode();
            if (status == 403) throw new IOException("Pareamento recusado. Confira o código no PC.");
            if (status == 503 && path.startsWith("/voz/")) {
                String notice = "O sintetizador do PC está indisponível.";
                try (InputStream error = connection.getErrorStream()) {
                    byte[] buffer = new byte[4096];
                    int count = error == null ? -1 : error.read(buffer);
                    if (count > 0) notice = new JSONObject(new String(buffer, 0, count, StandardCharsets.UTF_8)).optString("notice", notice);
                } catch (org.json.JSONException ignored) {}
                throw new IOException(notice);
            }
            if (status / 100 != 2) throw new IOException("Hub indisponível (" + status + ")");
            if (connection.getContentLength() > limit) throw new IOException("Resposta grande demais");
            try (InputStream in = connection.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[16384];
                for (int count; (count = in.read(buffer)) != -1;) {
                    if (out.size() + count > limit) throw new IOException("Resposta grande demais");
                    out.write(buffer, 0, count);
                }
                return out.toByteArray();
            }
        } finally { connection.disconnect(); }
    }
}
