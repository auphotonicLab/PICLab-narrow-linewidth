clear
clc

rootFolder = ...
"C:\Users\au617810\OneDrive - Aarhus universitet\O-drive - Jeppe\Coherent receiver";

files = dir(fullfile(rootFolder,"**","*.Wfm.csv"));
files = files(~contains({files.folder},"Variance_analysis"));

for k = 1:length(files)

    waveFile = fullfile(files(k).folder,files(k).name);

    [~,basename,~] = fileparts(files(k).name);

    % --------------------------------------------------
    % Find measurement number
    % --------------------------------------------------

    tok = regexp(basename,'no(\d+)','tokens');

    if isempty(tok)
        fprintf('Could not determine measurement number:\n%s\n',basename);
        continue
    end

    measurementNo = tok{1}{1};

    % --------------------------------------------------
    % Determine figure root
    % --------------------------------------------------

    if contains(files(k).folder,'29_07_2026 HHI Data')

        figureRoot = ...
        "C:\Users\au617810\OneDrive - Aarhus universitet\O-drive - Jeppe\Coherent receiver\29_07_2026_HHI_figures";

    elseif contains(files(k).folder,'31_07_2026 HHI Data')

        figureRoot = ...
        "C:\Users\au617810\OneDrive - Aarhus universitet\O-drive - Jeppe\Coherent receiver\31_07_2026_HHI_figures";

    else

        fprintf('Unknown data location:\n%s\n',files(k).folder);

        continue

    end

folderName = files(k).folder;

% --------------------------------------------------
% Figure folder mapping
% --------------------------------------------------

if contains(folderName,'PPCL Whisper')

    laserFolder = "PPCL Whisper";

    if contains(folderName,'30m')
        delayFolder = "PPCL_Whisper_delay_30m";
    elseif contains(folderName,'3km')
        delayFolder = "PPCL_Whisper_delay_3000m";
    else
        delayFolder = "PPCL_Whisper_delay_700m";
    end

elseif contains(folderName,'PPCL Dither')

    laserFolder = "PPCL Dither";

    if contains(folderName,'30m')
        delayFolder = "PPCL_Dither_delay_30m";
    elseif contains(folderName,'3km')
        delayFolder = "PPCL_Dither_delay_3000m";
    else
        delayFolder = "PPCL_Dither_delay_700m";
    end

elseif contains(folderName,'Agilent')

    laserFolder = "Agilent 81940A";

    if contains(folderName,'30m')
        delayFolder = "Agilent_81940A_delay_30m";
    elseif contains(folderName,'3km')
        delayFolder = "Agilent_81940A_delay_3000m";
    else
        delayFolder = "Agilent_delay_700m";
    end

elseif contains(folderName,'NKT')

    laserFolder = "NKT";

    if contains(folderName,'30m')
        delayFolder = "NKT_delay_30m";
    elseif contains(folderName,'3km')
        delayFolder = "NKT_delay_3000m";
    elseif contains(folderName,'10km')
        delayFolder = "NKT_delay_10000m";
    else
        delayFolder = "NKT_delay_700m";
    end

else

    fprintf('Unknown folder structure:\n%s\n',folderName);

    continue

end

    % --------------------------------------------------
    % Build output folder
    % --------------------------------------------------
    outFolder = fullfile(figureRoot,laserFolder,delayFolder,sprintf('No_%s',measurementNo),'Variance_analysis');

    fprintf('\n[%d/%d] Processing %s\n',k,length(files),basename);

    fprintf('Saving to:\n%s\n',outFolder);

    fprintf('\n');
    fprintf('Input : %s\n', waveFile);
    fprintf('Output: %s\n', outFolder);

    try

        variance_analysis(waveFile,outFolder);

    catch ME

        fprintf('\nFAILED: %s\n',waveFile);

        fprintf('%s\n',ME.getReport);

    end

end