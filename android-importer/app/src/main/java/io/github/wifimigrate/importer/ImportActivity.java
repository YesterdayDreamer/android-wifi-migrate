package io.github.wifimigrate.importer;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.wifi.WifiNetworkSuggestion;
import android.os.Bundle;
import android.provider.Settings;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Set;

public final class ImportActivity extends Activity {
    private static final int PICK = 1;
    private static final int SAVE = 2;
    private static final int REPORT = 3;
    private static final int BATCH_SIZE = 5;
    private static final int MAX_JSON = 16 * 1024 * 1024;
    private final ArrayList<WifiNetworkSuggestion> networks = new ArrayList<>();
    private final ArrayList<Integer> sourceIndices = new ArrayList<>();
    private final ArrayList<String> outcomes = new ArrayList<>();
    private final ArrayList<Integer> outcomeBatches = new ArrayList<>();
    private final ArrayList<String> outcomeReasons = new ArrayList<>();
    private final ArrayList<Integer> cancelledBatchIds = new ArrayList<>();
    private int batchNumber;
    private String sourceDigest;
    private int cancelledBatches;
    private TextView status;
    private Button next;
    private int cursor, pending, saved, existing, failed, unknown, skipped;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        ScrollView scroll = new ScrollView(this);
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        int gap = (int) (24 * getResources().getDisplayMetrics().density);
        panel.setPadding(gap, gap * 2, gap, gap);
        scroll.addView(panel);
        setContentView(scroll);
        TextView title = new TextView(this);
        title.setTextSize(24);
        title.setText("导入 Wi-Fi 网络");
        panel.addView(title);
        TextView hint = new TextView(this);
        hint.setText("选择明文 WiFi Password Manager JSON。每批最多 5 条，由系统确认。WPA2/WPA3 过渡网络只提交 WPA2 兼容项；OWE 过渡网络会跳过。");
        panel.addView(hint);
        Button open = new Button(this);
        open.setText("选择 JSON 文件");
        open.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*");
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            startActivityForResult(intent, PICK);
        });
        panel.addView(open);
        next = new Button(this);
        next.setText("请系统保存下一批");
        next.setEnabled(false);
        next.setOnClickListener(v -> saveNext());
        panel.addView(next);
        Button report = new Button(this);
        report.setText("保存结果报告");
        report.setOnClickListener(v -> {
            if (sourceDigest == null) {
                status.setText("请先打开一个导入文件。");
                return;
            }
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json");
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.putExtra(Intent.EXTRA_TITLE, "wifi-migrate-helper-result.json");
            startActivityForResult(intent, REPORT);
        });
        panel.addView(report);
        status = new TextView(this);
        panel.addView(status);
    }

    private static WifiNetworkSuggestion suggestion(JSONObject row) throws JSONException {
        if (!row.optBoolean("autojoin", true) || row.optBoolean("private", false)
                || !"AUTO".equals(row.optString("macRandomizationSetting", "AUTO"))
                || !"NONE".equals(row.optString("meteredOverride", "NONE"))) {
            throw new IllegalArgumentException("Settings require original importer");
        }
        JSONArray security = row.getJSONArray("security");
        Set<String> types = new HashSet<>();
        for (int i = 0; i < security.length(); i++) types.add(security.getString(i));
        WifiNetworkSuggestion.Builder builder = new WifiNetworkSuggestion.Builder()
                .setSsid(row.getString("ssid")).setIsHiddenSsid(row.optBoolean("hidden"));
        String key = row.getString("password");
        if (types.equals(Collections.singleton("WPA2")) || types.equals(new HashSet<>(Arrays.asList("WPA2", "WPA3")))) {
            if (key.length() < 8 || key.length() > 63) throw new IllegalArgumentException();
            builder.setWpa2Passphrase(key);
        } else if (types.equals(Collections.singleton("WPA3"))) {
            if (key.isEmpty() || key.equals("*")) throw new IllegalArgumentException();
            builder.setWpa3Passphrase(key);
        } else if (types.equals(Collections.singleton("OWE"))) {
            builder.setIsEnhancedOpen(true);
        } else if (!types.equals(Collections.singleton("OPEN"))) {
            throw new IllegalArgumentException();
        }
        return builder.build();
    }

    private void read(Intent data) throws IOException, JSONException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (InputStream input = getContentResolver().openInputStream(data.getData())) {
            if (input == null) throw new IOException();
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (bytes.size() + count > MAX_JSON) throw new IOException();
                bytes.write(buffer, 0, count);
            }
        }
        byte[] source = bytes.toByteArray();
        String text = new String(source, StandardCharsets.UTF_8);
        JSONArray rows = new JSONArray(text.startsWith("\uFEFF") ? text.substring(1) : text);
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(source);
            StringBuilder hex = new StringBuilder();
            for (byte value : digest) hex.append(String.format(java.util.Locale.ROOT, "%02x", value & 0xff));
            sourceDigest = hex.toString();
        } catch (NoSuchAlgorithmException error) {
            throw new IOException(error);
        }
        HashMap<String, Integer> counts = new HashMap<>();
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            if (row != null) counts.merge(row.optString("ssid"), 1, Integer::sum);
        }
        networks.clear();
        outcomes.clear();
        outcomeBatches.clear();
        outcomeReasons.clear();
        cancelledBatchIds.clear();
        batchNumber = 0;
        sourceIndices.clear();
        cancelledBatches = 0;
        cursor = pending = saved = existing = failed = unknown = skipped = 0;
        for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            outcomeBatches.add(0);
            try {
                if (row == null || counts.get(row.optString("ssid")) != 1) throw new IllegalArgumentException();
                networks.add(suggestion(row));
                sourceIndices.add(i);
                outcomes.add("NOT_STARTED");
                outcomeReasons.add(row.getJSONArray("security").length() == 2 ? "wpa2_compatibility_only" : "");
            } catch (IllegalArgumentException | JSONException error) {
                skipped++;
                outcomes.add("SKIPPED");
                outcomeReasons.add("unsupported_or_conflicting_configuration");
            }
        }
        updateStatus();
    }

    private void saveNext() {
        pending = Math.min(BATCH_SIZE, networks.size() - cursor);
        if (pending <= 0) return;
        Intent intent = new Intent(Settings.ACTION_WIFI_ADD_NETWORKS);
        intent.putParcelableArrayListExtra(Settings.EXTRA_WIFI_NETWORK_LIST,
                new ArrayList<>(networks.subList(cursor, cursor + pending)));
        next.setEnabled(false);
        try {
            startActivityForResult(intent, SAVE);
            batchNumber++;
        } catch (ActivityNotFoundException | SecurityException error) {
            pending = 0;
            next.setEnabled(true);
            status.setText("此固件无法打开系统导入界面。请改用 WiFi Password Manager 或系统扫码。");
        }
    }

    private void updateStatus() {
        next.setEnabled(cursor < networks.size() && pending == 0);
        status.setText("可处理 " + networks.size() + " 条，已提交 " + cursor
                + " 条\n系统报告保存 " + saved + "、已存在 " + existing + "、失败 " + failed
                + "、未知 " + unknown + "\n跳过 " + skipped + " 条（冲突、格式或设置不适用）");
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == PICK && result == RESULT_OK && data != null) {
            try {
                read(data);
            } catch (IOException | JSONException error) {
                networks.clear();
                outcomes.clear();
                sourceDigest = null;
                next.setEnabled(false);
                status.setText("无法读取明文 JSON。请重新选择文件。");
            }
        } else if (request == SAVE && pending > 0) {
            if (result == RESULT_OK) {
                ArrayList<Integer> results = data == null ? null
                        : data.getIntegerArrayListExtra(Settings.EXTRA_WIFI_NETWORK_RESULT_LIST);
                for (int i = 0; i < pending; i++) {
                    Integer code = results != null && i < results.size() ? results.get(i) : null;
                    String outcome;
                    if (code != null && code == Settings.ADD_WIFI_RESULT_SUCCESS) {
                        saved++; outcome = "SYSTEM_CONFIRMED";
                    } else if (code != null && code == Settings.ADD_WIFI_RESULT_ALREADY_EXISTS) {
                        existing++; outcome = "ALREADY_EXISTS";
                    } else if (code != null && code == Settings.ADD_WIFI_RESULT_ADD_OR_UPDATE_FAILED) {
                        failed++; outcome = "FAILED";
                    } else {
                        unknown++; outcome = "UNKNOWN";
                    }
                    outcomes.set(sourceIndices.get(cursor + i), outcome);
                    outcomeBatches.set(sourceIndices.get(cursor + i), batchNumber);
                    if (outcome.equals("FAILED") || outcome.equals("UNKNOWN")) {
                        outcomeReasons.set(sourceIndices.get(cursor + i),
                                code == null ? "missing_system_result" : "system_result_" + code);
                    }
                }
                cursor += pending;
            } else {
                cancelledBatches++;
                cancelledBatchIds.add(batchNumber);
            }
            pending = 0;
            updateStatus();
            if (result != RESULT_OK) status.append("\n此批未确认，可以重试。");
        } else if (request == REPORT && result == RESULT_OK && data != null && sourceDigest != null) {
            try (OutputStream output = getContentResolver().openOutputStream(data.getData())) {
                if (output == null) throw new IOException();
                JSONObject report = new JSONObject();
                report.put("format", "wifi-migrate-helper-v2");
                report.put("source_sha256", sourceDigest);
                report.put("cancelled_batches", cancelledBatches);
                report.put("cancelled_batch_ids", new JSONArray(cancelledBatchIds));
                report.put("source_count", outcomes.size());
                report.put("processed_count", cursor);
                report.put("unprocessed_count", outcomes.size() - cursor - skipped);
                JSONArray rows = new JSONArray();
                for (int i = 0; i < outcomes.size(); i++) {
                    JSONObject row = new JSONObject();
                    row.put("id", sourceDigest + ":" + (i + 1));
                    row.put("state", outcomes.get(i));
                    row.put("batch", outcomeBatches.get(i));
                    row.put("reason", outcomeReasons.get(i));
                    rows.put(row);
                }
                report.put("results", rows);
                output.write(report.toString(2).getBytes(StandardCharsets.UTF_8));
                status.append("\n已保存结果报告，可传回电脑。");
            } catch (IOException | JSONException error) {
                status.append("\n无法写入结果报告，请另选文件位置。");
            }
        }
    }
}
