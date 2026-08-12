%% ========================================================================
% Phase Increment Variance Analysis
%
% Input:
%    Tek / R&S waveform export:
%    *.Wfm.csv
%
% Channel mapping:
%    Ch1 = XI
%    Ch2 = XQ
%    Ch3 = YI
%    Ch4 = YQ
%
% Author: 
%% ========================================================================


function variance_analysis(waveFile, outFolder)

close all

if ~exist(outFolder,"dir")
    mkdir(outFolder)
end

% Save current folder
oldFolder = pwd;

% Change to output folder
cd(outFolder);


%% ------------------------------------------------------------------------
% OSCILLOSCOPE SETTINGS
%% ------------------------------------------------------------------------

dt = 50e-9;                    % 50 ns
%Fs = 1/dt;

fprintf('Loading waveform...\n')

%% ------------------------------------------------------------------------
% LOAD DATA
%% ------------------------------------------------------------------------

M = readmatrix(waveFile,'Delimiter',';');

XI = M(:,1);
XQ = M(:,2);
YI = M(:,3);
YQ = M(:,4);

N = length(XI);

fprintf('Loaded %.3f million samples\n',N/1e6);

%x = (0:N-1)'*dt;

%% ------------------------------------------------------------------------
% RECONSTRUCT PHASE INCREMENT
%% ------------------------------------------------------------------------

dphiX = unwrap(atan2(XQ,XI));
dphiY = unwrap(atan2(YQ,YI));

PX = mean(XI.^2 + XQ.^2);
PY = mean(YI.^2 + YQ.^2);

fprintf('Mean X power = %.3f\n',PX)
fprintf('Mean Y power = %.3f\n',PY)

if PX >= PY
    y = dphiX;
    disp('Using X polarization')
else
    y = dphiY;
    disp('Using Y polarization')
end

%% ------------------------------------------------------------------------
% WINDOW SETTINGS
%% ------------------------------------------------------------------------

Twin_list_min = 0.05;      % ms
Twin_list_max = 30;        % ms

Twin_list = logspace( ...
    log10(Twin_list_min/1000), ...
    log10(Twin_list_max/1000), ...
    20);

step_fraction = 0.1;

%% ------------------------------------------------------------------------
% MAIN ANALYSIS
%% ------------------------------------------------------------------------

mean_var = nan(size(Twin_list));
std_var  = nan(size(Twin_list));
n_win    = zeros(size(Twin_list));

all_var = cell(size(Twin_list));

fprintf('\n')
fprintf('Starting analysis...\n')

for k = 1:numel(Twin_list)

    Twin = Twin_list(k);

    fprintf('Window %2d/%2d : T = %.4f ms\n', ...
        k,numel(Twin_list),Twin*1e3);

    step = step_fraction*Twin;

    Ns_win  = round(Twin/dt);
    Ns_step = max(round(step/dt),1);

    start_idx = 1:Ns_step:(N-Ns_win);

    n_local = length(start_idx);

    var_local = nan(n_local,1);

    for m = 1:n_local

        idx = start_idx(m):(start_idx(m)+Ns_win-1);

        yy = y(idx);

        if numel(yy) > 10
            var_local(m) = var(yy,1);
        end

    end

    var_local = var_local(isfinite(var_local));

    all_var{k} = var_local;

    mean_var(k) = mean(var_local);
    std_var(k)  = std(var_local);
    n_win(k)    = numel(var_local);

end

%% ------------------------------------------------------------------------
% FIGURE 1
%% ------------------------------------------------------------------------

figure(1)
clf
hold on

set(gcf,'Units','centimeters')
set(gcf,'Position',[2 2 20 8])

errorbar( ...
    Twin_list*1e3, ...
    mean_var, ...
    std_var, ...
    'o-', ...
    'LineWidth',1.5, ...
    'Color','b');

xlabel('Observation-window duration T_{win} [ms]')
ylabel('Variance of \Delta\phi [rad^2]')

grid on

set(gca,'XScale','log')

set(gca,...
    'FontSize',14,...
    'FontName','Times New Roman',...
    'LineWidth',1.2,...
    'TickDir','out',...
    'Box','on',...
    'TickLength',[.015 0]);

xlim([5e-2 20])

pbaspect([5 1.5 1])

exportgraphics(gcf,...
    '1-Variance.pdf',...
    'ContentType','vector',...
    'BackgroundColor','white');
close(gcf)

%% ------------------------------------------------------------------------
% SAVE RESULTS
%% ------------------------------------------------------------------------

save('VarianceResults.mat',...
    'Twin_list',...
    'mean_var',...
    'std_var',...
    'n_win',...
    'all_var');

fprintf('\nFinished.\n')
fprintf('Saved:\n')
fprintf('   1-Variance.pdf\n')
fprintf('   VarianceResults.mat\n')


%% ========================================================================
% Figure 2
%% ========================================================================

figure(2); clf; hold on

set(gcf,'Units','centimeters','Position',[2 2 16 10]);
set(gcf,'PaperPositionMode','auto');

plot(Twin_list*1e3, std_var, ...
    'o-', ...
    'LineWidth',1.5, ...
    'Color','b');

xlabel('Observation-window duration T_{win} [ms]');
ylabel('Std. dev. of local variances [rad^2]');

grid on

set(gca,'XScale','log')

xlim([5e-2 20])

pbaspect([1.5 1.15 1])

set(gca,...
    'FontSize',14,...
    'FontName','Times New Roman',...
    'LineWidth',1.2,...
    'TickDir','out',...
    'Box','on',...
    'TickLength',[.015 0]);

exportgraphics(gcf,...
    '2-STD.pdf',...
    'ContentType','vector',...
    'BackgroundColor','white');

close(gcf)


%% ========================================================================
% Figure 3
%% ========================================================================

Twin_to_plot = 1e-4;      % 0.1 ms

Twin = Twin_to_plot;

step = step_fraction*Twin;

Ns_win  = round(Twin/dt);
Ns_step = max(round(step/dt),1);

start_idx = 1:Ns_step:(N-Ns_win);

var_local = nan(length(start_idx),1);

for m = 1:length(start_idx)

    idx = start_idx(m):(start_idx(m)+Ns_win-1);

    yy = y(idx);

    if numel(yy) > 10
        var_local(m) = var(yy,1);
    end

end

t_start = (start_idx-1)*dt;

figure(3); clf

plot(t_start*1e3,...
    var_local,...
    '.-',...
    'LineWidth',1.2,...
    'Color','b');

xlabel('Window start time [ms]');
ylabel('Variance of \Delta\phi [rad^2]');

title(sprintf('For T_{win}=%.1f ms',Twin*1e3));

grid on

set(gca,...
    'FontSize',12,...
    'FontName','Times New Roman',...
    'LineWidth',1.2,...
    'TickDir','out',...
    'Box','on',...
    'TickLength',[.015 0]);

ylim([0 6])

pbaspect([15 3 1])

exportgraphics(gcf,...
    '3-Variance-versus-start-time.pdf',...
    'ContentType','vector',...
    'BackgroundColor','white');
close(gcf)

%% ========================================================================
% Figure 4
%% ========================================================================

Twin = 2e-3;      % 2 ms

example_starts = [0 100 200 300]*1e-3;

figure(4); clf
hold on

COL = [
    0.00 0.00 1.00
    0.00 0.50 0.00
    1.00 0.55 0.00
    1.00 0.00 0.00
    ];

Ns_win = round(Twin/dt);

for m = 1:length(example_starts)

    start_sample = round(example_starts(m)/dt)+1;

    idx = start_sample:(start_sample+Ns_win-1);

    if idx(end) > N
        continue
    end

    yy = y(idx);

    histogram(yy,...
        'Normalization','pdf',...
        'DisplayStyle','stairs',...
        'LineWidth',2,...
        'EdgeColor',COL(m,:),...
        'NumBins',40);

end

xlabel('\Delta\phi [rad]');
ylabel('Probability density');

title(sprintf( ...
    'Histograms of \\Delta\\phi for T_{win}=%.1f ms',...
    Twin*1e3));

grid on

set(gca,...
    'FontSize',12,...
    'FontName','Times New Roman',...
    'LineWidth',1.2,...
    'TickDir','out',...
    'Box','on',...
    'TickLength',[.015 0]);

pbaspect([2 1 1])

legend( ...
    '0 ms',...
    '100 ms',...
    '200 ms',...
    '300 ms',...
    'Location','best');

exportgraphics(gcf,...
    '4-hist-versus-start-time.pdf',...
    'ContentType','vector',...
    'BackgroundColor','white');
close(gcf)


% ----- your existing script -----
% Use waveFile as input
% Save:
% 1-Variance.pdf
% 2-STD.pdf
% 3-Variance-versus-start-time.pdf
% 4-hist-versus-start-time.pdf
%
% and VarianceResults.mat
% -------------------------------

close all

%clearvars -except waveFile outFolder oldFolder

cd(oldFolder);

end
