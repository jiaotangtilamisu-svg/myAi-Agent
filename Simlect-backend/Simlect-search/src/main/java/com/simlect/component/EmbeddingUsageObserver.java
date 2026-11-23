package com.simlect.component;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import org.springframework.ai.embedding.observation.EmbeddingModelObservationContext;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Records provider usage only. Never logs input, vectors, headers, keys or exceptions. */
@Component
public class EmbeddingUsageObserver implements ObservationHandler<EmbeddingModelObservationContext> {
    private static final Logger log=LoggerFactory.getLogger(EmbeddingUsageObserver.class);
    @Override public boolean supportsContext(Observation.Context c){return c instanceof EmbeddingModelObservationContext;}
    @Override public void onStop(EmbeddingModelObservationContext c){
        var response=c.getResponse();
        var usage=response==null?null:response.getMetadata().getUsage();
        Integer dimension=response==null||response.getResults().isEmpty()?null:response.getResults().get(0).getOutput().length;
        log.info("embedding_usage model={} inputs={} vectors={} dimension={} promptTokens={} totalTokens={} result={}",
            response==null?"unavailable":response.getMetadata().getModel(),c.getRequest().getInstructions().size(),
            response==null?0:response.getResults().size(),dimension,usage==null?null:usage.getPromptTokens(),
            usage==null?null:usage.getTotalTokens(),c.getError()==null?"success":"error");
    }
}
