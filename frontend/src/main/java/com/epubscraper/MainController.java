package com.epubscraper;

import javafx.application.Platform;
import javafx.fxml.FXML;
import javafx.scene.control.*;
import javafx.stage.FileChooser;
import java.io.File;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class MainController {

    @FXML private TextField urlInput;
    @FXML private TextField titleInput;
    @FXML private TextField maxChaptersInput;
    @FXML private ProgressBar progressBar;
    @FXML private Label statusLabel;
    @FXML private Button startBtn;

    private final HttpClient httpClient = HttpClient.newHttpClient();
    
    // ĐỔI DÒNG NÀY THÀNH URL CỦA RENDER SAU KHI DEPLOY, VÍ DỤ: "https://my-app.onrender.com/api/v1"
    private final String API_BASE_URL = "http://localhost:8000/api/v1"; 
    
    private ScheduledExecutorService scheduler;

    @FXML
    public void startScrapingJob() {
        String url = urlInput.getText();
        String title = titleInput.getText();
        int maxChapters = Integer.parseInt(maxChaptersInput.getText().isEmpty() ? "100" : maxChaptersInput.getText());

        if (url.isEmpty() || title.isEmpty()) {
            statusLabel.setText("Lỗi: Vui lòng nhập đầy đủ URL và tên truyện!");
            return;
        }

        FileChooser fileChooser = new FileChooser();
        fileChooser.setTitle("Chọn nơi lưu sách ePub");
        fileChooser.setInitialFileName(title.replace(" ", "_") + ".epub");
        fileChooser.getExtensionFilters().add(new FileChooser.ExtensionFilter("ePub Files", "*.epub"));
        File saveFile = fileChooser.showSaveDialog(null);

        if (saveFile == null) return;

        startBtn.setDisable(true);
        statusLabel.setText("Đang gửi yêu cầu tới máy chủ Python...");

        String jsonPayload = String.format("{\"url\":\"%s\",\"title\":\"%s\",\"author\":\"Unknown\",\"max_chapters\":%d}", url, title, maxChapters);

        HttpRequest request = HttpRequest.newBuilder()
              .uri(URI.create(API_BASE_URL + "/scraper/jobs"))
              .header("Content-Type", "application/json")
              .POST(HttpRequest.BodyPublishers.ofString(jsonPayload))
              .build();

        httpClient.sendAsync(request, HttpResponse.BodyHandlers.ofString())
              .thenAccept(response -> {
                    if (response.statusCode() == 202) {
                        String body = response.body();
                        String jobId = body.split("\"job_id\":\"")[1].split("\"")[0];
                        
                        Platform.runLater(() -> statusLabel.setText("Đang chạy tác vụ nền... ID: " + jobId));
                        pollStatus(jobId, saveFile);
                    } else {
                        Platform.runLater(() -> {
                            statusLabel.setText("Lỗi máy chủ: " + response.statusCode());
                            startBtn.setDisable(false);
                        });
                    }
                })
              .exceptionally(e -> {
                    Platform.runLater(() -> {
                        statusLabel.setText("Không thể kết nối đến Backend Python!");
                        startBtn.setDisable(false);
                    });
                    return null;
                });
    }

    private void pollStatus(String jobId, File saveFile) {
        scheduler = Executors.newSingleThreadScheduledExecutor();
        
        scheduler.scheduleAtFixedRate(() -> {
            HttpRequest request = HttpRequest.newBuilder()
                  .uri(URI.create(API_BASE_URL + "/scraper/jobs/" + jobId))
                  .GET()
                  .build();

            httpClient.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                  .thenAccept(response -> {
                        String body = response.body();
                        String status = body.split("\"status\":\"")[1].split("\"")[0];
                        String message = body.split("\"message\":\"")[1].split("\"")[0];
                        int progress = Integer.parseInt(body.split("\"progress\":")[1].split(",")[0]);

                        Platform.runLater(() -> {
                            progressBar.setProgress(progress / 100.0);
                            statusLabel.setText(message + " (" + progress + "%)");
                        });

                        if (status.equals("completed")) {
                            scheduler.shutdown();
                            downloadEpub(jobId, saveFile);
                        } else if (status.equals("failed")) {
                            scheduler.shutdown();
                            Platform.runLater(() -> {
                                statusLabel.setText("Lỗi: Tiến trình thất bại!");
                                startBtn.setDisable(false);
                            });
                        }
                    });
        }, 1, 2, TimeUnit.SECONDS);
    }

    private void downloadEpub(String jobId, File saveFile) {
        Platform.runLater(() -> statusLabel.setText("Đang tải tệp ePub về máy..."));

        HttpRequest request = HttpRequest.newBuilder()
              .uri(URI.create(API_BASE_URL + "/ebooks/" + jobId + "/download"))
              .GET()
              .build();

        httpClient.sendAsync(request, HttpResponse.BodyHandlers.ofFile(saveFile.toPath()))
              .thenAccept(response -> {
                    Platform.runLater(() -> {
                        statusLabel.setText("Thành công! Đã lưu tại: " + saveFile.getAbsolutePath());
                        progressBar.setProgress(1.0);
                        startBtn.setDisable(false);
                    });
                })
              .exceptionally(e -> {
                    Platform.runLater(() -> {
                        statusLabel.setText("Lỗi trong quá trình lưu tệp!");
                        startBtn.setDisable(false);
                    });
                    return null;
                });
    }
}