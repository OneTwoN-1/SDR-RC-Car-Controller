filenames = {'Up.complex16s', 'Down.complex16s', 'Left.complex16s', 'Right.complex16s'};
titles = {'UP', 'DOWN', 'LEFT', 'RIGHT'};

Fs = 2e6;          % Sample Rate: 2 MSPS
windowSize = 100;  % Fereastra pentru moving average
b = (1/windowSize)*ones(1,windowSize);
a = 1;

figure('Name', 'SDR Signal Analysis - Toate Directiile', 'Position', [50, 50, 1200, 800]);

for k = 1:length(filenames)
    % --- 1. Incarcarea fisierului RAW I/Q ---
    fileID = fopen(filenames{k}, 'r');
    if fileID == -1
        warning(['Nu s-a putut deschide fisierul: ', filenames{k}]);
        continue;
    end
    raw_data = fread(fileID, 'int8'); 
    fclose(fileID);
    
    % signal is complex i+jq
    %The data format is [I, Q, I, Q, I, Q...]
    I = raw_data(1:2:end);
    Q = raw_data(2:2:end);
    complex_signal = I + 1i * Q;

    N = length(complex_signal); 
    t = (0:N-1) / Fs;

    % Plot in Domeniul Timp (PWM Envelope) 
    raw_magnitude = abs(complex_signal);
    smoothed_envelope = filter(b, a, raw_magnitude);
    
    % Plasare in grid 2x2 (Colturile: 1=Stanga-Sus, 2=Dreapta-Sus, 3=Stanga-Jos, 4=Dreapta-Jos)
    subplot(2, 2, k);
    plot(t * 1000, smoothed_envelope, 'LineWidth', 1.5); 
    title(['Direction: ', titles{k}], 'FontWeight', 'bold', 'FontSize', 14);
    xlabel('Time (ms)', 'FontSize', 11);
    ylabel('Amplitude', 'FontSize', 11);
    grid on;
    xlim([0, 50]); % Facem zoom pe primele 50 ms
    ylim([0, max(smoothed_envelope) * 1.15]); 
end

disp('>>> Analiza completa s-a terminat cu succes!');